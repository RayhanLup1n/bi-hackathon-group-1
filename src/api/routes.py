from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.data.commodity_data import get_all_commodities, get_commodity_data
from src.data.stok_db import list_stok_komoditas, list_semua_stok
from src.data.bmkg_db import (
    list_all_wilayah,
    list_cuaca_wilayah,
    list_peringatan_aktif,
    list_peringatan_history,
    get_cuaca_summary_komoditas,
    get_wilayah_produksi,
    list_cuaca_semua,
)
from src.engine.rca_engine import run_rca
from src.models.schemas import (
    RCAResult, CommodityData,
    BmkgWilayah, BmkgCuacaHarian, BmkgPeringatan, BmkgPeringatanAktif,
)

router = APIRouter(prefix="/api", tags=["RCA"])


# ─────────────────────────────────────────────────────────────────────────────
# KOMODITAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/commodities", summary="Daftar komoditas yang tersedia")
def list_commodities() -> list[str]:
    return get_all_commodities()


@router.get("/commodity/{key}", summary="Data lengkap satu komoditas")
def get_commodity(
    key: str,
    sim_date: Optional[date] = Query(default=None, description="Simulasi tanggal (YYYY-MM-DD)"),
) -> CommodityData:
    data = get_commodity_data(key, tanggal=sim_date)
    if not data:
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# RCA
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rca/{key}", summary="Jalankan RCA untuk satu komoditas")
def run_rca_endpoint(
    key: str,
    sim_date: Optional[date] = Query(default=None, description="Simulasi tanggal (YYYY-MM-DD)"),
) -> RCAResult:
    data = get_commodity_data(key, tanggal=sim_date)
    if not data:
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")
    return run_rca(data, today=sim_date)


@router.get("/rca", summary="Jalankan RCA untuk semua komoditas")
def run_rca_all(
    sim_date: Optional[date] = Query(default=None, description="Simulasi tanggal (YYYY-MM-DD)"),
) -> list[RCAResult]:
    results = []
    for key in get_all_commodities():
        data = get_commodity_data(key, tanggal=sim_date)
        if data:
            results.append(run_rca(data, today=sim_date))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# STOK — Simulasi tarikan API Badan Pangan / Bulog
# ─────────────────────────────────────────────────────────────────────────────

stok_router = APIRouter(prefix="/api/stok", tags=["Stok"])


@stok_router.get("", summary="Stok semua komoditas di semua kota")
def get_semua_stok(sim_date: Optional[date] = Query(None)) -> list[dict]:
    return list_semua_stok(sim_date)


@stok_router.get("/{key}", summary="Stok per kota untuk satu komoditas")
def get_stok_by_key(key: str, sim_date: Optional[date] = Query(None)) -> list[dict]:
    rows = list_stok_komoditas(key, sim_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# BMKG — Simulasi tarikan API BMKG
# ─────────────────────────────────────────────────────────────────────────────

bmkg_router = APIRouter(prefix="/api/bmkg", tags=["BMKG"])


@bmkg_router.get("/wilayah", summary="Daftar wilayah produksi komoditas")
def get_wilayah() -> list[BmkgWilayah]:
    return [BmkgWilayah(**w) for w in list_all_wilayah()]


@bmkg_router.get(
    "/cuaca/{kode_wilayah}",
    summary="Cuaca harian wilayah (N hari terakhir)",
)
def get_cuaca_wilayah(
    kode_wilayah: str,
    n_hari: int = Query(default=14, ge=1, le=52, description="Jumlah hari yang ditampilkan"),
) -> list[BmkgCuacaHarian]:
    rows = list_cuaca_wilayah(kode_wilayah, n_hari)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Wilayah '{kode_wilayah}' tidak ditemukan atau belum ada data cuaca",
        )
    return [BmkgCuacaHarian(**r) for r in rows]


@bmkg_router.get(
    "/peringatan",
    summary="Peringatan cuaca ekstrem aktif hari ini (atau tanggal simulasi)",
)
def get_peringatan_aktif(
    sim_date: Optional[date] = Query(default=None, description="Simulasi tanggal (YYYY-MM-DD)"),
) -> list[BmkgPeringatanAktif]:
    tgl = sim_date or date.today()
    rows = list_peringatan_aktif(tgl)
    return [BmkgPeringatanAktif(**r) for r in rows]


@bmkg_router.get(
    "/peringatan/history",
    summary="Riwayat peringatan cuaca N hari terakhir",
)
def get_peringatan_history(
    n_hari: int = Query(default=30, ge=1, le=90, description="Jangkauan hari ke belakang"),
) -> list[BmkgPeringatan]:
    rows = list_peringatan_history(n_hari)
    return [BmkgPeringatan(**r) for r in rows]


@bmkg_router.get(
    "/cuaca-all",
    summary="Cuaca semua wilayah dalam rentang N hari (untuk debug)",
)
def get_cuaca_all(
    sim_date: Optional[date] = Query(default=None, description="Tanggal akhir rentang (YYYY-MM-DD)"),
    n_hari: int = Query(default=7, ge=1, le=45, description="Jumlah hari ke belakang"),
) -> list[dict]:
    tgl = sim_date or date.today()
    return list_cuaca_semua(tgl, n_hari)


@bmkg_router.get(
    "/komoditas/{key}/wilayah-produksi",
    summary="Daftar wilayah produksi untuk komoditas",
)
def get_wilayah_produksi_endpoint(key: str) -> list[dict]:
    if key not in get_all_commodities():
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")
    return get_wilayah_produksi(key)


@bmkg_router.get(
    "/komoditas/{key}/cuaca",
    summary="Tren cuaca 7 hari terakhir untuk daerah produksi komoditas",
)
def get_cuaca_komoditas_trend(
    key: str,
    sim_date: Optional[date] = Query(default=None, description="Simulasi tanggal (YYYY-MM-DD)"),
    n_hari: int = Query(default=7, ge=1, le=30),
) -> list[dict]:
    if key not in get_all_commodities():
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")
    tgl = sim_date or date.today()
    return get_cuaca_summary_komoditas(key, tgl, n_hari)

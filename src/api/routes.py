"""
API routes for R.A.D.A.R Pangan.

Endpoints:
  /api/commodities              - list komoditas yang tersedia
  /api/commodity/{key}          - data lengkap satu komoditas
  /api/rca/{key}                - jalankan RCA satu komoditas
  /api/rca                      - jalankan RCA semua komoditas
  /api/prices/{comcat_id}/summary   - ringkasan harga terkini
  /api/prices/{comcat_id}/history   - histori harga harian
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.data.commodity_data import (
    get_all_commodities,
    get_commodity_data,
    get_price_summary,
    get_price_history,
    KOMODITAS_MAP,
)
from src.engine.rca_engine import run_rca
from src.models.schemas import RCAResult, CommodityData

router = APIRouter(prefix="/api", tags=["RCA & Harga"])
stok_router = APIRouter(prefix="/api/stok", tags=["Stok"])
bmkg_router = APIRouter(prefix="/api/bmkg", tags=["BMKG"])


# ─────────────────────────────────────────────────────────────────────────────
# KOMODITAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/commodities", summary="Daftar komoditas yang tersedia")
def list_commodities() -> list[dict]:
    """Return list of commodities with their keys and names."""
    # Ensure map is loaded
    if not KOMODITAS_MAP:
        from src.data.commodity_data import init_commodity_data
        init_commodity_data()
    return [
        {"key": key, "name": info["name"], "comcat_id": info["comcat_id"]}
        for key, info in KOMODITAS_MAP.items()
    ]


@router.get("/commodity/{key}", summary="Data lengkap satu komoditas")
def get_commodity(
    key: str,
    sim_date: Optional[date] = Query(
        default=None, description="Simulasi tanggal (YYYY-MM-DD)"
    ),
) -> CommodityData:
    data = get_commodity_data(key, tanggal=sim_date)
    if not data:
        raise HTTPException(
            status_code=404, detail=f"Komoditas '{key}' tidak ditemukan"
        )
    return data


# ─────────────────────────────────────────────────────────────────────────────
# RCA
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rca/{key}", summary="Jalankan RCA untuk satu komoditas")
def run_rca_endpoint(
    key: str,
    sim_date: Optional[date] = Query(
        default=None, description="Simulasi tanggal (YYYY-MM-DD)"
    ),
) -> RCAResult:
    data = get_commodity_data(key, tanggal=sim_date)
    if not data:
        raise HTTPException(
            status_code=404, detail=f"Komoditas '{key}' tidak ditemukan"
        )
    return run_rca(data, today=sim_date)


@router.get("/rca", summary="Jalankan RCA untuk semua komoditas")
def run_rca_all(
    sim_date: Optional[date] = Query(
        default=None, description="Simulasi tanggal (YYYY-MM-DD)"
    ),
) -> list[RCAResult]:
    results = []
    for key in get_all_commodities():
        data = get_commodity_data(key, tanggal=sim_date)
        if data:
            results.append(run_rca(data, today=sim_date))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# PRICES — Direct price data access (for dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/prices/{comcat_id}/summary",
    summary="Ringkasan harga terkini per kota",
)
def price_summary(
    comcat_id: str,
    sim_date: Optional[date] = Query(None),
) -> dict:
    result = get_price_summary(comcat_id, sim_date)
    if not result:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return result


@router.get(
    "/prices/{comcat_id}/history",
    summary="Histori harga harian (rata-rata nasional)",
)
def price_history(
    comcat_id: str,
    n_days: int = Query(default=30, ge=7, le=365),
    sim_date: Optional[date] = Query(None),
) -> list[dict]:
    return get_price_history(comcat_id, n_days, sim_date)


# ─────────────────────────────────────────────────────────────────────────────
# STOK — Placeholder (belum ada data real stok)
# ─────────────────────────────────────────────────────────────────────────────

@stok_router.get("", summary="Stok semua komoditas (placeholder)")
def get_semua_stok(sim_date: Optional[date] = Query(None)) -> list[dict]:
    return []


@stok_router.get("/{key}", summary="Stok per komoditas (placeholder)")
def get_stok_by_key(key: str, sim_date: Optional[date] = Query(None)) -> list[dict]:
    return []


# ─────────────────────────────────────────────────────────────────────────────
# BMKG — Placeholder (belum ada data real cuaca)
# ─────────────────────────────────────────────────────────────────────────────

@bmkg_router.get("/wilayah", summary="Daftar wilayah (placeholder)")
def get_wilayah() -> list[dict]:
    return []


@bmkg_router.get("/cuaca/{kode_wilayah}", summary="Cuaca wilayah (placeholder)")
def get_cuaca_wilayah(kode_wilayah: str, n_hari: int = Query(default=14)) -> list[dict]:
    return []


@bmkg_router.get("/peringatan", summary="Peringatan aktif (placeholder)")
def get_peringatan_aktif(sim_date: Optional[date] = Query(None)) -> list[dict]:
    return []


@bmkg_router.get("/peringatan/history", summary="Riwayat peringatan (placeholder)")
def get_peringatan_history(n_hari: int = Query(default=30)) -> list[dict]:
    return []


@bmkg_router.get("/cuaca-all", summary="Cuaca semua wilayah (placeholder)")
def get_cuaca_all(
    sim_date: Optional[date] = Query(None),
    n_hari: int = Query(default=7),
) -> list[dict]:
    return []


@bmkg_router.get("/komoditas/{key}/wilayah-produksi", summary="Wilayah produksi (placeholder)")
def get_wilayah_produksi_endpoint(key: str) -> list[dict]:
    return []


@bmkg_router.get("/komoditas/{key}/cuaca", summary="Cuaca komoditas (placeholder)")
def get_cuaca_komoditas_trend(
    key: str,
    sim_date: Optional[date] = Query(None),
    n_hari: int = Query(default=7),
) -> list[dict]:
    return []

"""
API routes for R.A.D.A.R Pangan.

Endpoints:
  /api/commodities              - list komoditas yang tersedia
  /api/commodity/{key}          - data lengkap satu komoditas
  /api/rca/{key}                - jalankan RCA satu komoditas
  /api/rca                      - jalankan RCA semua komoditas
  /api/prices/{comcat_id}/summary   - ringkasan harga terkini
  /api/prices/{comcat_id}/history   - histori harga harian
  /api/het/{key}                - HET status per komoditas
  /api/het                      - HET status semua komoditas
  /api/cuaca/{provinsi_id}      - data cuaca per provinsi (Open-Meteo)
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
from src.engine.het_monitor import check_het_status, check_het_all, get_het_summary
from src.data.weather_data import get_weather_for_rca, get_weather_summary
from src.models.schemas import RCAResult, CommodityData

router = APIRouter(prefix="/api", tags=["RCA & Harga"])
het_router = APIRouter(prefix="/api/het", tags=["HET Monitor"])
cuaca_router = APIRouter(prefix="/api/cuaca", tags=["Cuaca"])
stok_router = APIRouter(prefix="/api/stok", tags=["Stok"])


# ─────────────────────────────────────────────────────────────────────────────
# KOMODITAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/commodities", summary="Daftar komoditas yang tersedia")
def list_commodities() -> list[str]:
    """Return list of commodity keys (string) for backward compatibility with frontend."""
    # Ensure map is loaded
    if not KOMODITAS_MAP:
        from src.data.commodity_data import init_commodity_data
        init_commodity_data()
    return list(KOMODITAS_MAP.keys())


@router.get("/commodities/detail", summary="Daftar komoditas dengan detail")
def list_commodities_detail() -> list[dict]:
    """Return list of commodities with key, name, and comcat_id."""
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
# HET MONITOR — Bandingkan harga aktual vs HET reference
# ─────────────────────────────────────────────────────────────────────────────

@het_router.get(
    "",
    summary="HET status semua komoditas",
)
def get_het_all(
    sim_date: Optional[date] = Query(None),
) -> list[dict]:
    """Check HET status for all MVP commodities."""
    commodity_prices: dict[str, tuple[int, str]] = {}
    for key in get_all_commodities():
        data = get_commodity_data(key, tanggal=sim_date)
        if data:
            info = KOMODITAS_MAP.get(key, {})
            comcat_id = info.get("comcat_id", "")
            commodity_prices[comcat_id] = (data.price_now, data.name)

    results = check_het_all(commodity_prices)
    return [r.model_dump() for r in results]


@het_router.get(
    "/summary",
    summary="Ringkasan HET (count per status)",
)
def get_het_summary_endpoint(
    sim_date: Optional[date] = Query(None),
) -> dict:
    """Get summary of HET status across all commodities."""
    commodity_prices: dict[str, tuple[int, str]] = {}
    for key in get_all_commodities():
        data = get_commodity_data(key, tanggal=sim_date)
        if data:
            info = KOMODITAS_MAP.get(key, {})
            comcat_id = info.get("comcat_id", "")
            commodity_prices[comcat_id] = (data.price_now, data.name)

    results = check_het_all(commodity_prices)
    return get_het_summary(results)


@het_router.get(
    "/{key}",
    summary="HET status per komoditas",
)
def get_het_by_key(
    key: str,
    sim_date: Optional[date] = Query(None),
) -> dict:
    """Check HET status for one commodity."""
    data = get_commodity_data(key, tanggal=sim_date)
    if not data:
        raise HTTPException(status_code=404, detail=f"Komoditas '{key}' tidak ditemukan")

    info = KOMODITAS_MAP.get(key, {})
    comcat_id = info.get("comcat_id", "")
    result = check_het_status(comcat_id, data.price_now, data.name)
    return result.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# CUACA — Data cuaca dari Open-Meteo (real, bukan placeholder)
# ─────────────────────────────────────────────────────────────────────────────

@cuaca_router.get(
    "/{provinsi_id}",
    summary="Data cuaca per provinsi (Open-Meteo)",
)
def get_cuaca_by_provinsi(
    provinsi_id: int,
    sim_date: Optional[date] = Query(None),
    n_days: int = Query(default=7, ge=1, le=30),
) -> dict:
    """Get weather data and extreme detection for a province."""
    # Get RCA-style weather check
    rca_cuaca = get_weather_for_rca(provinsi_id, tanggal=sim_date)

    # Get daily detail for display
    daily = get_weather_summary(provinsi_id, tanggal=sim_date, n_days=n_days)

    return {
        "provinsi_id": provinsi_id,
        "ekstrem": rca_cuaca.ekstrem,
        "ringkasan": rca_cuaca.desc,
        "daerah": rca_cuaca.daerah,
        "detail": rca_cuaca.detail,
        "harian": daily,
    }


@cuaca_router.get(
    "",
    summary="Data cuaca semua provinsi target",
)
def get_cuaca_all_provinces(
    sim_date: Optional[date] = Query(None),
) -> list[dict]:
    """Get weather summary for all target provinces."""
    from etl.config.constants import TARGET_PROVINCE_IDS, PROVINCE_NAMES

    results = []
    for prov_id in TARGET_PROVINCE_IDS:
        rca_cuaca = get_weather_for_rca(prov_id, tanggal=sim_date)
        results.append({
            "provinsi_id": prov_id,
            "provinsi_nama": PROVINCE_NAMES.get(prov_id, f"Provinsi {prov_id}"),
            "ekstrem": rca_cuaca.ekstrem,
            "ringkasan": rca_cuaca.desc,
            "daerah": rca_cuaca.daerah,
        })
    return results


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
    # Target provinces for MVP (inline to avoid cross-layer import from etl/)
    target_provinces = {
        11: "Banten",
        12: "Jawa Barat",
        13: "DKI Jakarta",
        26: "Sulawesi Selatan",
    }

    results = []
    for prov_id, prov_nama in target_provinces.items():
        rca_cuaca = get_weather_for_rca(prov_id, tanggal=sim_date)
        results.append({
            "provinsi_id": prov_id,
            "provinsi_nama": prov_nama,
            "ekstrem": rca_cuaca.ekstrem,
            "ringkasan": rca_cuaca.desc,
            "daerah": rca_cuaca.daerah,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# ML PREDICTIONS — Read from app.ml_predictions
# ─────────────────────────────────────────────────────────────────────────────

predictions_router = APIRouter(prefix="/api/predictions", tags=["ML Predictions"])


@predictions_router.get(
    "",
    summary="Ambil prediksi ML dari tabel app.ml_predictions",
)
def get_predictions(
    komoditas_id: Optional[str] = Query(None),
    kota_id: Optional[int] = Query(None),
    limit: int = Query(default=30, ge=1, le=365),
) -> dict:
    """Read ML predictions from database. Returns empty if no data yet."""
    from src.data.database import db_cursor

    try:
        with db_cursor() as cur:
            cur.execute("""
                SELECT komoditas_id, kota_id, prediction_date, target_date,
                       predicted_price, confidence_lower, confidence_upper,
                       model_version, created_at
                FROM app.ml_predictions
                WHERE (%s IS NULL OR komoditas_id = %s)
                  AND (%s IS NULL OR kota_id = %s)
                ORDER BY target_date ASC
                LIMIT %s
            """, (komoditas_id, komoditas_id, kota_id, kota_id, limit))
            rows = cur.fetchall()

        predictions = [dict(r) for r in rows]
        # Convert date/datetime to string for JSON serialization
        for p in predictions:
            for key in ("prediction_date", "target_date", "created_at"):
                if p.get(key):
                    p[key] = str(p[key])

        return {"predictions": predictions, "total": len(predictions)}
    except Exception:
        # Return empty if table doesn't exist yet or any error
        return {"predictions": [], "total": 0}


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY — Validation checks on raw.harga_pangan
# ─────────────────────────────────────────────────────────────────────────────

data_quality_router = APIRouter(prefix="/api/data-quality", tags=["Data Quality"])


@data_quality_router.get(
    "",
    summary="Full data quality report (coverage + missing + outliers + duplicates)",
)
def get_quality_report() -> dict:
    """Run all data quality checks and return combined summary.

    Uses MVP komoditas filter by default. Queries BigQuery.
    """
    from src.data.data_quality import get_quality_summary

    try:
        return get_quality_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data quality check failed: {e}")


@data_quality_router.get(
    "/coverage",
    summary="Data coverage summary (row counts, date range per komoditas)",
)
def get_coverage() -> dict:
    from src.data.data_quality import get_data_coverage

    try:
        return get_data_coverage()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Coverage check failed: {e}")


@data_quality_router.get(
    "/outliers",
    summary="Price outliers (z-score > 3 from 30-day rolling mean)",
)
def get_outliers(
    z_threshold: float = Query(default=3.0, ge=1.0, le=10.0),
    last_n_days: int = Query(default=90, ge=7, le=365),
) -> dict:
    from src.data.data_quality import check_outliers

    try:
        items = check_outliers(z_threshold=z_threshold, last_n_days=last_n_days)
        return {"count": len(items), "z_threshold": z_threshold, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Outlier check failed: {e}")


@data_quality_router.get(
    "/missing",
    summary="Missing price dates in last N days",
)
def get_missing_dates(
    last_n_days: int = Query(default=30, ge=7, le=365),
) -> dict:
    from src.data.data_quality import check_missing_dates

    try:
        items = check_missing_dates(last_n_days=last_n_days)
        return {"count": len(items), "last_n_days": last_n_days, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Missing dates check failed: {e}")


@data_quality_router.get(
    "/duplicates",
    summary="Duplicate rows (same comcat_id + kota_id + tanggal)",
)
def get_duplicates() -> dict:
    from src.data.data_quality import check_duplicates

    try:
        items = check_duplicates()
        return {"count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicates check failed: {e}")


"""
MVP Orchestrator — application layer that assembles decision-support data.

This module coordinates existing data access, domain engines, and the new
priority engine to produce unified Recommendation objects for the MVP API.

Responsibilities:
  - Gather data from commodity_data, weather_data, HET, RCA, and ML proxy
  - Run priority engine per commodity × province combination
  - Handle graceful degradation (ML offline, data stale)
  - Produce overview aggregates and transparency contract

This is the ONLY module that should orchestrate across multiple engines.
Routes should delegate to this module, not call engines directly.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from src.domain.engines.het_monitor import check_het_status
from src.domain.engines.rca_engine import run_rca
from src.domain.engines.priority_engine import build_recommendation
from src.domain.schemas.decision import Recommendation
from src.infrastructure.postgres.commodity_data import (
    KOMODITAS_MAP,
    get_all_commodities,
    get_commodity_data,
    get_price_history,
)
from src.infrastructure.postgres.database import db_cursor

logger = logging.getLogger(__name__)

# ── Target provinces for MVP (matches routes.py) ───────────────────────────
MVP_PROVINCES: dict[int, str] = {
    11: "Banten",
    12: "Jawa Barat",
    13: "DKI Jakarta",
    26: "Sulawesi Selatan",
}


def _get_data_freshness() -> tuple[float, str]:
    """Check how fresh the latest price data is.

    Returns:
        (age_days, latest_date_iso_string)
    """
    with db_cursor() as cur:
        cur.execute("SELECT MAX(tanggal) AS latest FROM app.harga_pangan")
        row = cur.fetchone()

    if not row or not row["latest"]:
        return (999.0, "Tidak tersedia")

    latest: date = row["latest"]
    age_days = (date.today() - latest).days
    return (float(max(0, age_days)), latest.isoformat())


def _get_coverage_ratio() -> float:
    """Get approximate data coverage ratio based on recent data."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT comcat_id) AS komoditas_count,
                   COUNT(DISTINCT kota_id) AS kota_count
            FROM app.harga_pangan
            WHERE tanggal >= CURRENT_DATE - INTERVAL '7 days'
        """)
        row = cur.fetchone()

    if not row or not row["kota_count"]:
        return 0.0

    # MVP: 6 komoditas × ~20 cities minimum expected
    expected_cities = 6 * 4 * 4  # rough: 6 komoditas × 4 prov × ~4 cities
    actual = row["kota_count"]
    return round(min(1.0, actual / max(1, expected_cities)), 2)


def _check_ml_health() -> bool:
    """Check if ML inference server is reachable."""
    try:
        import httpx
        ml_url = "http://localhost:8001/health"
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(ml_url)
            return resp.status_code == 200
    except Exception:
        return False


def _try_get_ml_forecast(
    komoditas_nama: str,
    kota_nama: str,
    tanggal: date,
) -> dict[str, Any] | None:
    """Attempt to get ML forecast for a commodity-city pair.

    Returns None if ML server is unreachable (graceful degradation).
    """
    import json
    try:
        import httpx
        ml_url = "http://localhost:8001/api/v1/analyze"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(ml_url, json={
                "komoditas_nama": komoditas_nama,
                "kota_nama": kota_nama,
                "tanggal": str(tanggal),
            })
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.debug("ML forecast unavailable for %s/%s: %s", komoditas_nama, kota_nama, exc)
    return None


def get_overview(
    sim_date: date | None = None,
) -> dict[str, Any]:
    """Build the Executive Dashboard overview contract.

    Returns aggregated data for all MVP commodities and provinces:
      - region status
      - data freshness
      - summary counts (risk levels)
      - top 3 priorities
      - review bundles
      - latest reviews

    This is the main endpoint response for /api/mvp/overview.
    """
    today = sim_date or date.today()
    data_age_days, data_latest = _get_data_freshness()
    coverage_ratio = _get_coverage_ratio()
    ml_online = _check_ml_health()

    # ── Build recommendations for all commodity x province combos ──────
    recommendations: list[Recommendation] = []
    commodity_keys = get_all_commodities()

    for key in commodity_keys:
        info = KOMODITAS_MAP.get(key, {})
        comcat_id = info.get("comcat_id", "")
        commodity_name = info.get("name", key)

        for prov_id, prov_name in MVP_PROVINCES.items():
            # Get commodity data filtered by province
            data = get_commodity_data(key, tanggal=today, province_id=prov_id)
            if not data:
                continue

            # HET check
            het_result = check_het_status(comcat_id, data.price_now, commodity_name)
            het_pct = het_result.pct_of_het
            het_status = het_result.status.value

            # RCA analysis
            rca_result = run_rca(data, today=today)

            # Weather signal
            has_extreme_weather = data.cuaca.ekstrem

            # City spread
            cities_total = len(data.kota_list)
            cities_rising = sum(1 for k in data.kota_list if k.naik)

            # Price delta
            if data.price_prev and data.price_prev > 0:
                price_delta_pct = (
                    (data.price_now - data.price_prev) / data.price_prev * 100
                )
            else:
                price_delta_pct = 0.0

            # ML forecast - try for the main city in this province
            forecast_data: dict[str, Any] | None = None
            if ml_online and cities_total > 0:
                main_city = data.kota_list[0].nama if data.kota_list else "Jakarta"
                forecast_data = _try_get_ml_forecast(commodity_name, main_city, today)

            # Extract ML signals
            forecast_breach = False
            forecast_p50 = None
            forecast_p90 = None
            model_version = ""
            model_wape = None
            model_worse = False

            if forecast_data:
                try:
                    result = forecast_data.get("result", forecast_data)
                    forecast_p50 = result.get("p50_7d")
                    forecast_p90 = result.get("p90_7d")
                    forecast_breach = result.get("breach_risk", False)
                    model_version = result.get("model_version", "")
                    model_wape = result.get("wape")
                except (AttributeError, KeyError, TypeError):
                    pass

            # Build recommendation per province
            rec = build_recommendation(
                commodity_key=key,
                commodity_name=commodity_name,
                province=prov_name,
                province_id=prov_id,
                het_pct=het_pct,
                het_status=het_status,
                price_now=data.price_now,
                price_prev=data.price_prev,
                price_delta_pct=price_delta_pct,
                is_anomaly=rca_result.is_anomaly,
                cities_total=cities_total,
                cities_rising=cities_rising,
                has_extreme_weather=has_extreme_weather,
                weather_detail=data.cuaca.desc,
                forecast_breach=forecast_breach,
                forecast_p50=forecast_p50,
                forecast_p90=forecast_p90,
                model_version=model_version,
                model_wape=model_wape,
                model_worse_than_baseline=model_worse,
                data_age_days=data_age_days,
                coverage_ratio=coverage_ratio,
                rca_diagnosis=rca_result.diagnosis.value,
                rca_severity=rca_result.severity_level,
                today=today,
            )
            recommendations.append(rec)

    # ── Sort by display priority score (descending) ──────────────────────
    recommendations.sort(key=lambda r: r.display_priority_score, reverse=True)

    # ── Summary counts ──────────────────────────────────────────────────
    risk_counts: dict[str, int] = {"kritis": 0, "tinggi": 0, "sedang": 0, "rendah": 0}
    for rec in recommendations:
        risk_counts[rec.risk_level] = risk_counts.get(rec.risk_level, 0) + 1

    # ── Top 3 priorities (diversified by commodity) ────────────────────
    top_3: list[dict[str, Any]] = []
    seen_commodities: set[str] = set()
    # First pass: pick highest-scoring entry per unique commodity
    for r in recommendations:
        if r.commodity not in seen_commodities and len(top_3) < 3:
            top_3.append(r.model_dump(mode="json"))
            seen_commodities.add(r.commodity)
    # If fewer than 3 unique commodities, fill remaining slots by score
    if len(top_3) < 3:
        for r in recommendations:
            if len(top_3) >= 3:
                break
            r_dict = r.model_dump(mode="json")
            if r_dict not in top_3:
                top_3.append(r_dict)

    # ── Review bundles ──────────────────────────────────────────────────
    from src.application.mvp_bundles import generate_bundles

    rec_dicts = [r.model_dump(mode="json") for r in recommendations]
    bundles = generate_bundles(rec_dicts)

    # ── Latest reviews ──────────────────────────────────────────────────
    try:
        from src.infrastructure.postgres.review_repository import get_latest_reviews
        latest_reviews = get_latest_reviews(limit=5)
    except Exception as exc:
        logger.warning("Latest reviews unavailable: %s", exc)
        latest_reviews = []

    # Unique commodity count (not commodity x province)
    unique_commodities = len({r.commodity for r in recommendations})

    return {
        "region": "Nasional",
        "provinces": [
            {"id": pid, "name": pname} for pid, pname in MVP_PROVINCES.items()
        ],
        "data_freshness": {
            "latest_date": data_latest,
            "age_days": data_age_days,
            "coverage_ratio": coverage_ratio,
            "status": (
                "fresh" if data_age_days <= 1
                else "stale" if data_age_days <= 3
                else "very_stale"
            ),
        },
        "service_health": {
            "database": "ok",  # we're querying it
            "ml_service": "online" if ml_online else "offline",
        },
        "summary": {
            "total_commodities": unique_commodities,
            "total_entries": len(recommendations),
            "risk_counts": risk_counts,
            "has_critical": risk_counts["kritis"] > 0,
            "has_high": risk_counts["tinggi"] > 0,
        },
        "top_priorities": top_3,
        "review_bundles": bundles,
        "latest_reviews": latest_reviews,
    }


def get_priorities(
    sim_date: date | None = None,
    province_filter: str | None = None,
    risk_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Get ranked list of all recommendations with optional filters.

    Produces one recommendation per commodity per province (not just national).
    Used by /api/mvp/priorities endpoint.
    """
    today = sim_date or date.today()
    data_age_days, _ = _get_data_freshness()
    coverage_ratio = _get_coverage_ratio()
    ml_online = _check_ml_health()

    results: list[dict[str, Any]] = []
    commodity_keys = get_all_commodities()

    # Resolve province filter to ID for early query-level filtering
    target_provinces: dict[int, str] = {}
    if province_filter:
        for pid, pname in MVP_PROVINCES.items():
            if province_filter.lower() == pname.lower():
                target_provinces = {pid: pname}
                break
        # If no match found, return empty (no province matches filter)
        if not target_provinces:
            return []
    else:
        target_provinces = MVP_PROVINCES

    for key in commodity_keys:
        info = KOMODITAS_MAP.get(key, {})
        comcat_id = info.get("comcat_id", "")
        commodity_name = info.get("name", key)

        for prov_id, prov_name in target_provinces.items():
            data = get_commodity_data(key, tanggal=today, province_id=prov_id)
            if not data:
                continue

            het_result = check_het_status(comcat_id, data.price_now, commodity_name)
            rca_result = run_rca(data, today=today)

            price_delta_pct = 0.0
            if data.price_prev and data.price_prev > 0:
                price_delta_pct = (
                    (data.price_now - data.price_prev) / data.price_prev * 100
                )

            cities_total = len(data.kota_list)
            cities_rising = sum(1 for k in data.kota_list if k.naik)

            rec = build_recommendation(
                commodity_key=key,
                commodity_name=commodity_name,
                province=prov_name,
                province_id=prov_id,
                het_pct=het_result.pct_of_het,
                het_status=het_result.status.value,
                price_now=data.price_now,
                price_prev=data.price_prev,
                price_delta_pct=price_delta_pct,
                is_anomaly=rca_result.is_anomaly,
                cities_total=cities_total,
                cities_rising=cities_rising,
                has_extreme_weather=data.cuaca.ekstrem,
                weather_detail=data.cuaca.desc,
                data_age_days=data_age_days,
                coverage_ratio=coverage_ratio,
                rca_diagnosis=rca_result.diagnosis.value,
                rca_severity=rca_result.severity_level,
                today=today,
            )

            # Apply risk filter
            if risk_filter and rec.risk_level != risk_filter.lower():
                continue

            results.append(rec.model_dump(mode="json"))

    # Sort by display priority score descending
    results.sort(key=lambda r: r["display_priority_score"], reverse=True)

    # Add rank
    for i, r in enumerate(results, start=1):
        r["rank"] = i

    return results


def get_priority_detail(
    recommendation_id: str,
    sim_date: date | None = None,
) -> dict[str, Any] | None:
    """Get full detail for a single recommendation.

    Includes price history and review status if available.
    """
    today = sim_date or date.today()

    # Get all recommendations and find the matching one
    priorities = get_priorities(sim_date=today)
    rec_dict = next(
        (p for p in priorities if p["recommendation_id"] == recommendation_id),
        None,
    )
    if rec_dict is None:
        return None

    # Attach price history for charts
    commodity_key = rec_dict.get("commodity", "").lower().replace(" ", "_")
    info = KOMODITAS_MAP.get(commodity_key, {})
    comcat_id = info.get("comcat_id", "")

    if comcat_id:
        price_history = get_price_history(comcat_id, n_days=30, target_date=today)
        rec_dict["price_history"] = price_history

    # Attach review status
    try:
        from src.infrastructure.postgres.review_repository import get_review
        review = get_review(recommendation_id)
        rec_dict["review"] = review
    except Exception:
        rec_dict["review"] = None

    return rec_dict


def get_transparency() -> dict[str, Any]:
    """Build the data & model transparency contract.

    Used by /api/mvp/transparency endpoint.
    """
    from config.settings import (
        HET_KRITIS_PCT,
        HET_MELAMPAUI_PCT,
        HET_REFERENCE,
        HET_WASPADA_PCT,
    )

    data_age_days, data_latest = _get_data_freshness()
    coverage_ratio = _get_coverage_ratio()

    return {
        "data_sources": [
            {
                "name": "PIHPS",
                "type": "Harga Pangan Harian",
                "update_cadence": "Harian (t+1)",
                "latest_data": data_latest,
                "coverage": f"{coverage_ratio:.0%}",
                "notes": "Data harga dari pasar tradisional di kota-kota terpilih",
            },
            {
                "name": "Open-Meteo",
                "type": "Cuaca Historis",
                "update_cadence": "Harian",
                "latest_data": data_latest,
                "coverage": "4 provinsi target MVP",
                "notes": "Data cuaca untuk deteksi kondisi ekstrem",
            },
            {
                "name": "python-holidays",
                "type": "Kalender Hari Besar",
                "update_cadence": "Tahunan",
                "latest_data": "2026-2027",
                "coverage": "Nasional",
                "notes": "91 hari besar nasional (2024-2027)",
            },
            {
                "name": "HET Reference",
                "type": "Harga Eceran Tertinggi",
                "update_cadence": "Manual",
                "latest_data": "Estimasi berdasarkan observasi pasar",
                "coverage": "6 komoditas MVP",
                "notes": "Sumber: estimasi Bapanas. Perlu validasi resmi.",
            },
        ],
        "model": {
            "type": "LightGBM Quantile Regression",
            "version": "see ML service /health for runtime version",
            "horizons": [7, 14],
            "outputs": ["P50", "P90"],
            "metrics": {
                "wape_note": (
                    "WAPE/MAE akan ditampilkan setelah ML pipeline "
                    "tersambung dan evaluasi dilakukan"
                ),
                "baseline_note": (
                    "Baseline: last-value naive. Model harus lebih baik "
                    "dari baseline untuk rekomendasi dengan confidence tinggi."
                ),
            },
        },
        "priority_config": {
            "weights": {
                "price_position": 0.25,
                "forecast_p90_breach": 0.30,
                "momentum_anomaly": 0.20,
                "regional_spread": 0.15,
                "weather_calendar": 0.10,
            },
            "confidence_weights": {
                "freshness": 0.30,
                "coverage": 0.25,
                "history": 0.20,
                "model_performance": 0.25,
            },
            "confidence_levels": {
                "high": ">= 0.80",
                "medium": ">= 0.55 and < 0.80",
                "low": "< 0.55",
            },
            "risk_thresholds": {
                "rendah": "0–24",
                "sedang": "25–49",
                "tinggi": "50–74",
                "kritis": "75–100",
            },
            "het_thresholds": {
                "waspada": f">= {HET_WASPADA_PCT * 100:.0f}% HET",
                "kritis": f">= {HET_KRITIS_PCT * 100:.0f}% HET",
                "melampaui": f"> {HET_MELAMPAUI_PCT * 100:.0f}% HET",
            },
            "het_reference_prices": {
                comcat_id: {"price": price, "unit": "Rp/kg"}
                for comcat_id, price in HET_REFERENCE.items()
            },
        },
        "known_limitations": [
            "Data stok bersumber dari agregat nasional (bukan per-provinsi atau real-time)",
            "HET reference mengacu pada Peraturan Bapanas No. 12/2024",
            "Forecast ML menggunakan model statistik, bukan simulasi pasar",
            "Korelasi cuaca bukan bukti kausal",
            "Response options adalah rekomendasi tinjauan, bukan instruksi kebijakan",
            "Confidence rendah membatasi response pada 'Verifikasi'",
        ],
        "knowledge_status_note": (
            "Semua bobot, threshold, dan konfigurasi adalah INTERNAL_HYPOTHESIS. "
            "Nilai aktual perlu divalidasi melalui pilot dengan domain expert."
        ),
    }


def get_service_status() -> dict[str, Any]:
    """Aggregate service health check.

    Used by /api/mvp/service-status endpoint.
    """
    ml_online = _check_ml_health()
    data_age_days, data_latest = _get_data_freshness()

    db_ok = False
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if (db_ok and data_age_days < 7) else "degraded",
        "database": {
            "connected": db_ok,
            "type": "PostgreSQL",
        },
        "data_freshness": {
            "latest_data": data_latest,
            "age_days": data_age_days,
            "is_stale": data_age_days > 2,
        },
        "ml_service": {
            "online": ml_online,
            "url": "http://localhost:8001",
        },
        "timestamp": datetime.now().isoformat(),
    }


# ── Search & Export delegates ──────────────────────────────────────────────

def search_priorities(
    query: str,
    sim_date: date | None = None,
    max_results: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search all recommendations by keyword query.

    Delegates to search_service after building the full priority list.
    """
    from src.application.mvp_search import search_recommendations

    priorities = get_priorities(sim_date=sim_date)
    return search_recommendations(
        priorities=priorities,
        query=query,
        max_results=max_results,
        offset=offset,
    )


def export_priorities_file(
    fmt: str,
    recommendation_id: str | None = None,
    sim_date: date | None = None,
) -> tuple[bytes, str, str]:
    """Generate an export file (CSV or Excel) for priorities.

    Args:
        fmt: "csv" or "xlsx".
        recommendation_id: If set, export single recommendation detail.
        sim_date: Optional simulation date.

    Returns:
        Tuple of (content_bytes, media_type, filename).
    """
    from src.application.mvp_export import (
        export_priorities_csv,
        export_priorities_xlsx,
        export_single_csv,
        export_single_xlsx,
    )

    today = sim_date or date.today()
    now_ts = today.isoformat()

    if recommendation_id:
        # Single recommendation export
        detail = get_priority_detail(recommendation_id, sim_date=sim_date)
        if not detail:
            raise ValueError(f"Recommendation '{recommendation_id}' tidak ditemukan.")

        # Fetch review for single export
        review = None
        try:
            from src.infrastructure.postgres.review_repository import get_review
            review = get_review(recommendation_id)
        except Exception:
            pass

        commodity = detail.get("commodity", "unknown").replace(" ", "_")
        safe_id = recommendation_id.replace(" ", "_")

        if fmt == "csv":
            content = export_single_csv(detail, review=review)
            filename = f"RADAR_Pangan_{commodity}_{safe_id}_{now_ts}.csv"
            return (content, "text/csv; charset=utf-8", filename)
        else:
            content = export_single_xlsx(detail, review=review)
            filename = f"RADAR_Pangan_{commodity}_{safe_id}_{now_ts}.xlsx"
            return (
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename,
            )
    else:
        # All priorities export
        priorities = get_priorities(sim_date=sim_date)

        # Collect reviews
        reviews: dict[str, Any] = {}
        try:
            from src.infrastructure.postgres.review_repository import get_review
            for rec in priorities:
                rid = rec.get("recommendation_id", "")
                if rid:
                    r = get_review(rid)
                    if r:
                        reviews[rid] = r
        except Exception:
            pass

        if fmt == "csv":
            content = export_priorities_csv(priorities, reviews=reviews)
            filename = f"RADAR_Pangan_Prioritas_{now_ts}.csv"
            return (content, "text/csv; charset=utf-8", filename)
        else:
            content = export_priorities_xlsx(priorities, reviews=reviews)
            filename = f"RADAR_Pangan_Prioritas_{now_ts}.xlsx"
            return (
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename,
            )


# ── Sparkline data ─────────────────────────────────────────────────────────

def get_sparklines(
    sim_date: date | None = None,
    n_days: int = 14,
) -> dict[str, Any]:
    """Get compact sparkline data for all commodity x province combos.

    Returns price history per recommendation_id suitable for
    lightweight inline sparkline charts on the dashboard.
    Single query per commodity avoids N+1 problem.

    Args:
        sim_date: Reference date (default today).
        n_days: Number of days to include (default 14).

    Returns:
        Dict with sparklines (dict[recommendation_id, list[price]]) and metadata.
    """
    today = sim_date or date.today()
    commodity_keys = get_all_commodities()
    sparklines: dict[str, list[float | None]] = {}
    labels: list[str] = []

    for key in commodity_keys:
        info = KOMODITAS_MAP.get(key, {})
        comcat_id = info.get("comcat_id", "")
        if not comcat_id:
            continue

        for prov_id, prov_name in MVP_PROVINCES.items():
            rec_id = f"rec_{today.isoformat()}_{key}_{prov_name.replace(' ', '_').lower()}"
            history = get_price_history(comcat_id, n_days=n_days, target_date=today)

            if not labels and history:
                labels = [str(row["tanggal"]) for row in history]

            prices: list[float | None] = []
            if history:
                prices = [
                    float(row["avg_harga"]) if row["avg_harga"] else None
                    for row in history
                ]
            sparklines[rec_id] = prices

    return {
        "labels": labels,
        "sparklines": sparklines,
        "n_days": n_days,
        "reference_date": today.isoformat(),
    }

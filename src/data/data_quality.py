"""
Data quality checks for raw.harga_pangan.

Provides validation functions to detect:
  - Missing price data (gaps in dates per komoditas/kota)
  - Price outliers (z-score > 3 from rolling 30-day mean)
  - Duplicate rows (same komoditas + kota + tanggal)
  - Coverage summary (date range, row counts per komoditas/kota)

All queries target BigQuery raw.harga_pangan with required partition filter.
Uses parameterized queries (ArrayQueryParameter) to prevent SQL injection.
"""
from __future__ import annotations

import logging
import math
from datetime import date
from typing import Optional

from google.cloud.bigquery import ArrayQueryParameter, ScalarQueryParameter

from src.data.bigquery_client import bq_query

logger = logging.getLogger(__name__)

# MVP komoditas IDs for default filtering
_MVP_COMCAT = ("com_11", "com_12", "com_13", "com_14", "com_15", "com_16")


def _comcat_params(comcat_ids: Optional[list[str]] = None) -> list[str]:
    """Resolve comcat_ids to a list — defaults to MVP komoditas."""
    return list(comcat_ids) if comcat_ids else list(_MVP_COMCAT)


def get_data_coverage(
    comcat_ids: Optional[list[str]] = None,
) -> dict:
    """Get data coverage summary: row counts, date range per komoditas.

    Returns a dict with 'total_rows', 'date_range', 'per_komoditas' list.
    """
    ids = _comcat_params(comcat_ids)

    sql = """
    SELECT
        comcat_id,
        MIN(tanggal) AS first_date,
        MAX(tanggal) AS last_date,
        COUNT(*) AS row_count,
        COUNT(DISTINCT kota_id) AS kota_count,
        COUNT(DISTINCT tanggal) AS date_count
    FROM `raw.harga_pangan`
    WHERE tanggal >= '2020-01-01'
        AND comcat_id IN UNNEST(@comcat_ids)
    GROUP BY comcat_id
    ORDER BY comcat_id
    """
    params = [ArrayQueryParameter("comcat_ids", "STRING", ids)]
    rows = bq_query(sql, params=params)

    total_rows = sum(r["row_count"] for r in rows)
    all_first = min((r["first_date"] for r in rows), default=None)
    all_last = max((r["last_date"] for r in rows), default=None)

    return {
        "total_rows": total_rows,
        "date_range": {
            "first": str(all_first) if all_first else None,
            "last": str(all_last) if all_last else None,
        },
        "per_komoditas": [
            {
                "comcat_id": r["comcat_id"],
                "row_count": r["row_count"],
                "kota_count": r["kota_count"],
                "date_count": r["date_count"],
                "first_date": str(r["first_date"]),
                "last_date": str(r["last_date"]),
            }
            for r in rows
        ],
    }


def check_missing_dates(
    comcat_ids: Optional[list[str]] = None,
    last_n_days: int = 30,
) -> list[dict]:
    """Find komoditas+kota combos that have missing dates in recent N days.

    Returns list of dicts with comcat_id, kota_id, expected_dates, actual_dates,
    missing_count, missing_pct.
    """
    if not (1 <= last_n_days <= 730):
        raise ValueError(f"last_n_days must be in [1, 730], got {last_n_days}")

    ids = _comcat_params(comcat_ids)

    sql = """
    WITH date_range AS (
        SELECT
            MAX(tanggal) AS max_date,
            DATE_SUB(MAX(tanggal), INTERVAL @n_days DAY) AS min_date
        FROM `raw.harga_pangan`
        WHERE tanggal >= '2020-01-01'
    ),
    expected AS (
        -- Only count weekdays (Mon-Sat, PIHPS doesn't report Sundays)
        SELECT d
        FROM date_range,
        UNNEST(GENERATE_DATE_ARRAY(min_date, max_date)) AS d
        WHERE EXTRACT(DAYOFWEEK FROM d) NOT IN (1)  -- exclude Sunday (1=Sun in BQ)
    ),
    expected_count AS (
        SELECT COUNT(*) AS cnt FROM expected
    ),
    actual AS (
        SELECT
            comcat_id,
            kota_id,
            tanggal
        FROM `raw.harga_pangan`, date_range
        WHERE tanggal >= date_range.min_date
            AND tanggal <= date_range.max_date
            AND tanggal >= '2020-01-01'
            AND comcat_id IN UNNEST(@comcat_ids)
        GROUP BY comcat_id, kota_id, tanggal
    ),
    combos AS (
        SELECT DISTINCT comcat_id, kota_id
        FROM actual
    )
    SELECT
        c.comcat_id,
        c.kota_id,
        e.cnt AS expected_dates,
        COUNT(a.tanggal) AS actual_dates,
        e.cnt - COUNT(a.tanggal) AS missing_count,
        ROUND(
            (1.0 - CAST(COUNT(a.tanggal) AS FLOAT64) /
            NULLIF(e.cnt, 0)) * 100, 1
        ) AS missing_pct
    FROM combos c
    CROSS JOIN expected_count e
    LEFT JOIN actual a ON c.comcat_id = a.comcat_id
        AND c.kota_id = a.kota_id
    GROUP BY c.comcat_id, c.kota_id, e.cnt
    HAVING e.cnt - COUNT(a.tanggal) > 0
    ORDER BY missing_count DESC
    LIMIT 50
    """
    params = [
        ArrayQueryParameter("comcat_ids", "STRING", ids),
        ScalarQueryParameter("n_days", "INT64", last_n_days),
    ]
    return bq_query(sql, params=params)


def check_outliers(
    comcat_ids: Optional[list[str]] = None,
    z_threshold: float = 3.0,
    last_n_days: int = 90,
) -> list[dict]:
    """Find price outliers using z-score from rolling 30-day window.

    Returns rows where |z-score| > threshold, sorted by abs(z_score) desc.
    """
    # Guard against invalid float values (nan, inf)
    if not math.isfinite(z_threshold) or not (0.5 <= z_threshold <= 20.0):
        raise ValueError(
            f"z_threshold must be a finite number in [0.5, 20.0], got {z_threshold}"
        )
    if not (1 <= last_n_days <= 730):
        raise ValueError(f"last_n_days must be in [1, 730], got {last_n_days}")

    ids = _comcat_params(comcat_ids)

    sql = """
    WITH latest AS (
        SELECT MAX(tanggal) AS max_date
        FROM `raw.harga_pangan`
        WHERE tanggal >= '2020-01-01'
    ),
    recent AS (
        SELECT
            h.comcat_id,
            h.kota_id,
            h.tanggal,
            h.harga,
            AVG(h.harga) OVER (
                PARTITION BY h.comcat_id, h.kota_id
                ORDER BY h.tanggal
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS rolling_avg,
            STDDEV_SAMP(h.harga) OVER (
                PARTITION BY h.comcat_id, h.kota_id
                ORDER BY h.tanggal
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS rolling_std
        FROM `raw.harga_pangan` h
        CROSS JOIN latest
        WHERE h.tanggal >= DATE_SUB(latest.max_date, INTERVAL @n_days DAY)
            AND h.tanggal >= '2020-01-01'
            AND h.comcat_id IN UNNEST(@comcat_ids)
    )
    SELECT
        comcat_id,
        kota_id,
        tanggal,
        CAST(harga AS INT64) AS harga,
        CAST(ROUND(rolling_avg) AS INT64) AS rolling_avg,
        ROUND((harga - rolling_avg) / NULLIF(rolling_std, 0), 2) AS z_score
    FROM recent
    WHERE rolling_std > 0
        AND ABS((harga - rolling_avg) / rolling_std) > @z_threshold
    ORDER BY ABS((harga - rolling_avg) / NULLIF(rolling_std, 0)) DESC
    LIMIT 50
    """
    params = [
        ArrayQueryParameter("comcat_ids", "STRING", ids),
        ScalarQueryParameter("n_days", "INT64", last_n_days),
        ScalarQueryParameter("z_threshold", "FLOAT64", z_threshold),
    ]
    rows = bq_query(sql, params=params)

    # Convert date objects to strings for JSON serialization
    for row in rows:
        if isinstance(row.get("tanggal"), date):
            row["tanggal"] = str(row["tanggal"])

    return rows


def check_duplicates(
    comcat_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Find duplicate rows (same comcat_id + kota_id + tanggal).

    Returns list of dicts with comcat_id, kota_id, tanggal, dup_count.
    """
    ids = _comcat_params(comcat_ids)

    sql = """
    SELECT
        comcat_id,
        kota_id,
        tanggal,
        COUNT(*) AS dup_count
    FROM `raw.harga_pangan`
    WHERE tanggal >= '2020-01-01'
        AND comcat_id IN UNNEST(@comcat_ids)
    GROUP BY comcat_id, kota_id, tanggal
    HAVING COUNT(*) > 1
    ORDER BY dup_count DESC
    LIMIT 50
    """
    params = [ArrayQueryParameter("comcat_ids", "STRING", ids)]
    rows = bq_query(sql, params=params)

    for row in rows:
        if isinstance(row.get("tanggal"), date):
            row["tanggal"] = str(row["tanggal"])

    return rows


def get_quality_summary(
    comcat_ids: Optional[list[str]] = None,
) -> dict:
    """Run all quality checks and return a combined summary.

    Returns dict with coverage, missing_dates, outliers, duplicates counts.
    """
    ids = _comcat_params(comcat_ids)

    coverage = get_data_coverage(ids)
    missing = check_missing_dates(ids, last_n_days=30)
    outliers = check_outliers(ids, z_threshold=3.0, last_n_days=90)
    duplicates = check_duplicates(ids)

    return {
        "coverage": coverage,
        "missing_dates": {
            "count": len(missing),
            "items": missing[:20],  # top 20
        },
        "outliers": {
            "count": len(outliers),
            "items": outliers[:20],  # top 20
        },
        "duplicates": {
            "count": len(duplicates),
            "items": duplicates[:10],  # top 10
        },
        "overall_status": _compute_status(
            missing_count=len(missing),
            outlier_count=len(outliers),
            duplicate_count=len(duplicates),
        ),
    }


def _compute_status(
    missing_count: int,
    outlier_count: int,
    duplicate_count: int,
) -> str:
    """Compute overall data quality status."""
    if duplicate_count > 0:
        return "WARNING"
    if missing_count > 10 or outlier_count > 20:
        return "WARNING"
    if missing_count > 0 or outlier_count > 0:
        return "OK_WITH_NOTES"
    return "GOOD"

"""
BigQuery client wrapper for FastAPI.

Provides a shared BigQuery client instance and helper functions
for querying the data warehouse (raw/staging/marts datasets).

Authentication: Application Default Credentials (ADC).
  Setup: gcloud auth application-default login

Usage:
    from src.data.bigquery_client import bq_query, bq_query_one

    # Multiple rows
    rows = bq_query("SELECT * FROM `raw.harga_pangan` WHERE tanggal >= '2020-01-01' LIMIT 10")

    # Single row
    row = bq_query_one("SELECT COUNT(*) as cnt FROM `raw.harga_pangan` WHERE tanggal >= '2020-01-01'")

    # Parameterized query (BigQuery uses @param syntax)
    from google.cloud.bigquery import ScalarQueryParameter
    rows = bq_query(
        "SELECT * FROM `raw.harga_pangan` WHERE comcat_id = @comcat_id AND tanggal >= '2020-01-01'",
        params=[ScalarQueryParameter("comcat_id", "STRING", "com_13")],
    )
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

logger = logging.getLogger(__name__)

# ── Module-level client (lazy init, thread-safe) ─────────────────────────────

_client: Optional[bigquery.Client] = None
_lock = threading.Lock()

# Default timeout for BigQuery queries (seconds)
BQ_QUERY_TIMEOUT = 60

# ── Thread-safe TTL cache ─────────────────────────────────────────────────────

_cache: dict[str, tuple[list[dict], datetime]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL_MINUTES = 5
_CACHE_MAX_ENTRIES = 200


def get_bq_client() -> bigquery.Client:
    """Get or create the shared BigQuery client (thread-safe singleton).

    Reads GCP_PROJECT and BQ_LOCATION from env vars lazily (at first call),
    so they work correctly even if _load_env() hasn't run yet at import time.
    """
    global _client
    if _client is None:
        with _lock:
            # Double-checked locking: re-check inside lock
            if _client is None:
                project = os.getenv("GCP_PROJECT", "radar-pangan-hackathon")
                location = os.getenv("BQ_LOCATION", "asia-southeast2")
                _client = bigquery.Client(
                    project=project,
                    location=location,
                )
                logger.info(
                    "BigQuery client initialized (project=%s, location=%s)",
                    project, location,
                )
    return _client


def close_bq_client() -> None:
    """Close the BigQuery client. Call at app shutdown."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None
            logger.info("BigQuery client closed")


def bq_query(
    sql: str,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
    timeout: int = BQ_QUERY_TIMEOUT,
) -> list[dict]:
    """
    Execute a BigQuery SQL query and return results as list of dicts.

    Args:
        sql: BigQuery SQL query string.
             Use @param_name for parameterized queries.
             IMPORTANT: queries on raw.harga_pangan MUST include
             WHERE tanggal >= '2020-01-01' (partition filter required).
        params: Optional list of ScalarQueryParameter for parameterized queries.
        timeout: Query timeout in seconds (default: 60s).

    Returns:
        List of dicts (column_name -> value).

    Raises:
        GoogleAPIError: If BigQuery query fails (quota, permission, syntax).
        TimeoutError: If query exceeds timeout.
    """
    client = get_bq_client()

    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = params

    try:
        query_job = client.query(sql, job_config=job_config)
        rows = query_job.result(timeout=timeout)
        return [dict(row) for row in rows]
    except GoogleAPIError as e:
        logger.error("BigQuery query failed: %s | SQL: %.200s", e, sql)
        raise
    except TimeoutError:
        logger.error("BigQuery query timed out after %ds | SQL: %.200s", timeout, sql)
        raise


def bq_query_one(
    sql: str,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
    timeout: int = BQ_QUERY_TIMEOUT,
) -> Optional[dict]:
    """
    Execute a BigQuery query and return the first row as dict, or None.

    Convenience wrapper around bq_query() for single-row results.
    """
    results = bq_query(sql, params, timeout=timeout)
    return results[0] if results else None


def bq_query_cached(
    sql: str,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
    timeout: int = BQ_QUERY_TIMEOUT,
    ttl_minutes: int = _CACHE_TTL_MINUTES,
) -> list[dict]:
    """
    Execute a BigQuery query with thread-safe TTL caching.

    Same interface as bq_query(), but caches results in memory.
    Repeated identical queries return cached results until TTL expires.
    Useful for dashboard endpoints that hit the same data repeatedly.

    Args:
        sql: BigQuery SQL query string.
        params: Optional list of ScalarQueryParameter.
        timeout: Query timeout in seconds.
        ttl_minutes: Cache TTL in minutes (default: 5).

    Returns:
        List of dicts (column_name -> value), possibly from cache.
    """
    # Build cache key from SQL + params
    cache_key = f"{sql}|{str(params)}"

    # Check cache (read path - short lock)
    with _cache_lock:
        if cache_key in _cache:
            result, expire_at = _cache[cache_key]
            if datetime.now() < expire_at:
                logger.debug("BQ cache HIT: %.80s", sql)
                return result

    # Cache miss - execute query (outside lock to avoid blocking)
    logger.debug("BQ cache MISS: %.80s", sql)
    result = bq_query(sql, params, timeout=timeout)

    # Store in cache (write path - short lock)
    with _cache_lock:
        # Evict oldest entries if cache is full
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            oldest_key = min(_cache, key=lambda k: _cache[k][1])
            del _cache[oldest_key]
        _cache[cache_key] = (result, datetime.now() + timedelta(minutes=ttl_minutes))

    return result


def clear_bq_cache() -> None:
    """Clear all cached BigQuery results. Call when data is refreshed."""
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
        if count:
            logger.info("Cleared %d BigQuery cache entries", count)

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
    from google.cloud.bigquery import ScalarQueryParameter, QueryJobConfig
    rows = bq_query(
        "SELECT * FROM `raw.harga_pangan` WHERE comcat_id = @comcat_id AND tanggal >= '2020-01-01'",
        params=[ScalarQueryParameter("comcat_id", "STRING", "com_13")],
    )
"""
from __future__ import annotations

import os
from typing import Optional

from google.cloud import bigquery

# ── Module-level client (lazy init) ──────────────────────────────────────────

_client: Optional[bigquery.Client] = None

GCP_PROJECT = os.getenv("GCP_PROJECT", "radar-pangan-hackathon")
BQ_LOCATION = os.getenv("BQ_LOCATION", "asia-southeast2")


def get_bq_client() -> bigquery.Client:
    """Get or create the shared BigQuery client (singleton)."""
    global _client
    if _client is None:
        _client = bigquery.Client(
            project=GCP_PROJECT,
            location=BQ_LOCATION,
        )
    return _client


def close_bq_client() -> None:
    """Close the BigQuery client. Call at app shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def bq_query(
    sql: str,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
) -> list[dict]:
    """
    Execute a BigQuery SQL query and return results as list of dicts.

    Args:
        sql: BigQuery SQL query string.
             Use @param_name for parameterized queries.
             IMPORTANT: queries on raw.harga_pangan MUST include
             WHERE tanggal >= '2020-01-01' (partition filter required).
        params: Optional list of ScalarQueryParameter for parameterized queries.

    Returns:
        List of dicts (column_name -> value).
    """
    client = get_bq_client()

    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = params

    query_job = client.query(sql, job_config=job_config)
    rows = query_job.result()

    return [dict(row) for row in rows]


def bq_query_one(
    sql: str,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
) -> Optional[dict]:
    """
    Execute a BigQuery query and return the first row as dict, or None.

    Convenience wrapper around bq_query() for single-row results.
    """
    results = bq_query(sql, params)
    return results[0] if results else None

"""
Migrate raw data from Supabase PostgreSQL to Google BigQuery.

Exports all raw.* tables from Supabase and batch-loads them into BigQuery.
Tables in BigQuery must already exist (created by Terraform in infra/).

Strategy:
  - Export from Supabase via SELECT * (using psycopg2)
  - Load to BigQuery via load_table_from_dataframe() — batch load is FREE
  - Each table is loaded independently with progress logging
  - Idempotent: uses WRITE_TRUNCATE to replace existing data

Prerequisites:
  1. Terraform applied: cd infra/ && terraform apply
  2. GCP auth: gcloud auth application-default login
  3. Supabase credentials in .envs/.env
  4. Dependencies: uv sync (google-cloud-bigquery, pandas, psycopg2-binary)

Usage:
    cd bi-hackathon-group-1
    uv run python etl/scripts/migrate_to_bigquery.py
    uv run python etl/scripts/migrate_to_bigquery.py --table harga_pangan  # single table
    uv run python etl/scripts/migrate_to_bigquery.py --dry-run             # preview only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

import pandas as pd
from google.cloud import bigquery
from loguru import logger

# Ensure project root is in path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "etl"))

# Load Supabase credentials
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".envs", ".env"))

import psycopg2
import psycopg2.extras

# ── Configuration ─────────────────────────────────────────────────────────────

GCP_PROJECT = "radar-pangan-hackathon"
BQ_DATASET = "raw"
BQ_LOCATION = "asia-southeast2"


@dataclass
class TableMigration:
    """Definition for a single table migration."""
    pg_table: str           # e.g. "raw.harga_pangan"
    bq_table: str           # e.g. "harga_pangan"
    description: str
    order_by: str = "id"    # ORDER BY clause for consistent export


# Tables to migrate (raw layer only — staging/marts handled by dbt)
TABLES: list[TableMigration] = [
    TableMigration(
        pg_table="raw.dim_provinsi",
        bq_table="dim_provinsi",
        description="Master provinsi (4 rows)",
        order_by="provinsi_id",
    ),
    TableMigration(
        pg_table="raw.dim_kota",
        bq_table="dim_kota",
        description="Master kota (18 rows)",
        order_by="kota_id",
    ),
    TableMigration(
        pg_table="raw.hari_besar",
        bq_table="hari_besar",
        description="Hari libur nasional (91 rows)",
        order_by="id",
    ),
    TableMigration(
        pg_table="raw.cuaca_harian",
        bq_table="cuaca_harian",
        description="Cuaca harian Open-Meteo (11K+ rows)",
        order_by="id",
    ),
    TableMigration(
        pg_table="raw.harga_pangan",
        bq_table="harga_pangan",
        description="Harga pangan BI PIHPS (619K+ rows)",
        order_by="id",
    ),
    TableMigration(
        pg_table="raw.pipeline_log",
        bq_table="pipeline_log",
        description="Pipeline audit trail",
        order_by="id",
    ),
]


def _get_pg_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")
    return f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"


def export_from_postgres(table: TableMigration) -> pd.DataFrame:
    """
    Export a table from Supabase PostgreSQL into a DataFrame.

    Uses server-side cursor for memory efficiency on large tables.
    """
    logger.info(f"Exporting {table.pg_table} from Supabase...")

    conn = psycopg2.connect(_get_pg_dsn())
    try:
        query = f"SELECT * FROM {table.pg_table} ORDER BY {table.order_by}"  # noqa: S608
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    logger.info(f"  Exported {len(df):,} rows, {len(df.columns)} columns")
    return df


def _fix_dtypes_for_bigquery(df: pd.DataFrame, table: TableMigration) -> pd.DataFrame:
    """
    Fix pandas dtypes to be compatible with BigQuery load.

    BigQuery client expects:
      - datetime/date columns as proper pandas types (not object)
      - no timezone info on timestamps (BQ handles UTC)
      - NaN in integer columns handled (use Int64 nullable)
    """
    df = df.copy()

    # Drop the PostgreSQL auto-increment 'id' column — BigQuery schema uses INT64 REQUIRED,
    # but we provide our own IDs from Supabase. Keep the id column as-is.

    # Convert date columns
    date_cols = ["tanggal", "tanggal_mulai", "tanggal_selesai",
                 "berlaku_mulai", "berlaku_sampai", "prediction_date", "target_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date

    # Convert timestamp columns — remove timezone if present
    ts_cols = ["_extracted_at", "started_at", "finished_at", "created_at"]
    for col in ts_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True).dt.tz_localize(None)

    # Convert integer columns to Int64 (nullable) to handle NaN
    int_cols = ["id", "provinsi_id", "kota_id", "pasar_tipe", "tahun", "bulan",
                "records_inserted", "bulan_mulai", "bulan_selesai"]
    for col in int_cols:
        if col in df.columns:
            df[col] = df[col].astype("Int64")

    # Convert float columns — ensure float64
    float_cols = ["harga", "latitude", "longitude", "precipitation_sum", "rain_sum",
                  "temperature_max", "temperature_min", "wind_speed_max",
                  "et0_evapotranspiration", "sunshine_duration",
                  "inflasi_mtm", "inflasi_ytd", "predicted_price",
                  "confidence_lower", "confidence_upper", "het_harga"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_to_bigquery(
    client: bigquery.Client,
    df: pd.DataFrame,
    table: TableMigration,
) -> int:
    """
    Load DataFrame into BigQuery table using batch load (FREE).

    Uses WRITE_TRUNCATE for idempotent full refresh.
    Returns number of rows loaded.
    """
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{table.bq_table}"
    logger.info(f"Loading {len(df):,} rows into {table_ref}...")

    # Fix dtypes for BigQuery compatibility
    df = _fix_dtypes_for_bigquery(df, table)

    # Configure load job — WRITE_TRUNCATE replaces existing data
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    # Load using load_table_from_dataframe (batch — FREE)
    load_job = client.load_table_from_dataframe(
        df,
        table_ref,
        job_config=job_config,
        location=BQ_LOCATION,
    )

    # Wait for the job to complete
    load_job.result()

    # Verify row count
    dest_table = client.get_table(table_ref)
    logger.success(f"  Loaded {dest_table.num_rows:,} rows into {table_ref}")
    return dest_table.num_rows


def migrate_table(
    client: bigquery.Client,
    table: TableMigration,
    dry_run: bool = False,
) -> dict:
    """
    Migrate a single table from Supabase to BigQuery.

    Returns a summary dict with table name, row count, and duration.
    """
    t_start = time.time()

    # Step 1: Export from Supabase
    df = export_from_postgres(table)

    if df.empty:
        logger.warning(f"  {table.pg_table} is empty — skipping.")
        return {"table": table.bq_table, "rows": 0, "duration": 0, "status": "empty"}

    if dry_run:
        logger.info(f"  [DRY RUN] Would load {len(df):,} rows to {BQ_DATASET}.{table.bq_table}")
        logger.info(f"  Columns: {list(df.columns)}")
        logger.info(f"  Sample:\n{df.head(3).to_string()}")
        return {"table": table.bq_table, "rows": len(df), "duration": 0, "status": "dry_run"}

    # Step 2: Load to BigQuery
    rows_loaded = load_to_bigquery(client, df, table)

    duration = time.time() - t_start
    return {
        "table": table.bq_table,
        "rows": rows_loaded,
        "duration": duration,
        "status": "success",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate raw data from Supabase PostgreSQL to BigQuery"
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Migrate a single table (e.g. 'harga_pangan'). Default: all tables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview data without loading to BigQuery.",
    )
    args = parser.parse_args()

    # Validate environment
    if not os.getenv("SUPABASE_HOST"):
        logger.error("SUPABASE_HOST not set. Copy .envs/.env.example to .envs/.env and fill in.")
        sys.exit(1)

    # Select tables to migrate
    tables = TABLES
    if args.table:
        tables = [t for t in TABLES if t.bq_table == args.table]
        if not tables:
            valid = [t.bq_table for t in TABLES]
            logger.error(f"Table '{args.table}' not found. Valid: {valid}")
            sys.exit(1)

    # Initialize BigQuery client
    client = None
    if not args.dry_run:
        client = bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)
        logger.info(f"BigQuery client initialized: project={GCP_PROJECT}, location={BQ_LOCATION}")

    # Migrate each table
    t_total = time.time()
    results: list[dict] = []

    print()
    print("=" * 70)
    print("SUPABASE -> BIGQUERY MIGRATION")
    print("=" * 70)
    print(f"  Project:  {GCP_PROJECT}")
    print(f"  Dataset:  {BQ_DATASET}")
    print(f"  Location: {BQ_LOCATION}")
    print(f"  Tables:   {len(tables)}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)
    print()

    for i, table in enumerate(tables, 1):
        logger.info(f"[{i}/{len(tables)}] {table.description}")
        try:
            result = migrate_table(client, table, dry_run=args.dry_run)
            results.append(result)
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            results.append({
                "table": table.bq_table,
                "rows": 0,
                "duration": 0,
                "status": f"error: {e}",
            })
        print()

    # Summary
    total_duration = time.time() - t_total
    total_rows = sum(r["rows"] for r in results)
    success_count = sum(1 for r in results if r["status"] == "success")

    print("=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"  {'Table':<25} {'Rows':>10}  {'Time':>8}  {'Status'}")
    print(f"  {'-'*25} {'-'*10}  {'-'*8}  {'-'*10}")
    for r in results:
        duration_str = f"{r['duration']:.1f}s" if r["duration"] > 0 else "—"
        print(f"  {r['table']:<25} {r['rows']:>10,}  {duration_str:>8}  {r['status']}")
    print(f"  {'-'*25} {'-'*10}  {'-'*8}")
    print(f"  {'TOTAL':<25} {total_rows:>10,}  {total_duration:.1f}s")
    print()
    print(f"  Result: {success_count}/{len(results)} tables migrated successfully")
    print("=" * 70)

    if any(r["status"].startswith("error") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

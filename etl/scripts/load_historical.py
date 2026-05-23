"""
Load historical PIHPS data ke BigQuery raw.harga_pangan.

Batch strategy: per kota per tahun agar aman dari OOM.
Load strategy: BigQuery batch load via load_table_from_dataframe (FREE).

Usage:
    cd bi-hackathon-group-1
    python -X utf8 etl/scripts/load_historical.py
    python -X utf8 etl/scripts/load_historical.py --start-year 2023
    python -X utf8 etl/scripts/load_historical.py --resume
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

# Ensure etl/ is in path for relative imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load credentials from .envs/.env
from dotenv import load_dotenv
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, ".envs", ".env"))

import pandas as pd
from google.cloud import bigquery
from loguru import logger

from extractors.pihps_extractor import PihpsExtractor
from config.constants import TARGET_PROVINCE_IDS


# -- Config --------------------------------------------------------------------

DEFAULT_START_YEAR = 2020
DEFAULT_END_YEAR = 2026

GCP_PROJECT = os.getenv("GCP_PROJECT", "radar-pangan-hackathon")
BQ_LOCATION = os.getenv("BQ_LOCATION", "asia-southeast2")
BQ_TABLE_HARGA = f"{GCP_PROJECT}.raw.harga_pangan"
BQ_TABLE_LOG = f"{GCP_PROJECT}.raw.pipeline_log"


def _get_bq_client() -> bigquery.Client:
    """Create BigQuery client with project config."""
    return bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)


def _get_next_id(client: bigquery.Client, table_ref: str) -> int:
    """Get next available ID for a BigQuery table."""
    # pipeline_log is partitioned by started_at, need partition filter
    if "pipeline_log" in table_ref:
        query = f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_ref}` WHERE started_at >= '2020-01-01'"
    elif "harga_pangan" in table_ref:
        query = f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_ref}` WHERE tanggal >= '2020-01-01'"
    else:
        query = f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_ref}`"
    result = client.query(query).result()
    row = next(iter(result))
    return row[0]


def _load_to_bigquery(
    client: bigquery.Client,
    df: pd.DataFrame,
    table_ref: str,
) -> int:
    """Load DataFrame into BigQuery using batch load (FREE).

    Uses WRITE_APPEND to add new data incrementally.
    dbt staging layer handles deduplication.
    """
    if df.empty:
        return 0

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    load_job = client.load_table_from_dataframe(
        df,
        table_ref,
        job_config=job_config,
    )

    # Wait for job to complete
    load_job.result()
    return load_job.output_rows


def _log_pipeline_run(
    client: bigquery.Client,
    run_id: str,
    pipeline_name: str,
    tanggal_mulai: date | None,
    tanggal_selesai: date | None,
    records_inserted: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Log pipeline run to BigQuery raw.pipeline_log."""
    try:
        next_id = _get_next_id(client, BQ_TABLE_LOG)
        now = datetime.utcnow()
        df_log = pd.DataFrame([{
            "id": next_id,
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "tanggal_mulai": tanggal_mulai,
            "tanggal_selesai": tanggal_selesai,
            "records_inserted": records_inserted,
            "status": status,
            "error_message": error_message,
            "started_at": now,
            "finished_at": now,
        }])

        # Fix dtypes for BigQuery
        df_log["id"] = df_log["id"].astype("Int64")
        df_log["records_inserted"] = df_log["records_inserted"].astype("Int64")

        _load_to_bigquery(client, df_log, BQ_TABLE_LOG)
    except Exception as e:
        logger.warning(f"Failed to log pipeline run: {e}")


def _extract_prov_year(
    extractor: PihpsExtractor,
    prov_id: int,
    year: int,
) -> pd.DataFrame:
    """Extract data for one province, one year. Returns DataFrame."""
    tanggal_mulai = date(year, 1, 1)
    tanggal_selesai = min(date(year, 12, 31), date.today() - timedelta(days=1))

    if tanggal_mulai > tanggal_selesai:
        return pd.DataFrame()

    df = extractor.extract_harga_per_wilayah(
        tanggal_mulai=tanggal_mulai,
        tanggal_selesai=tanggal_selesai,
        province_ids=[prov_id],
    )

    if df.empty:
        return pd.DataFrame()

    # Deduplicate
    df = df.drop_duplicates(
        subset=["tanggal", "comcat_id", "kota_id", "pasar_nama"],
        keep="last",
    )

    return df


def _prepare_dataframe(df: pd.DataFrame, start_id: int) -> pd.DataFrame:
    """Prepare DataFrame for BigQuery load with proper dtypes."""
    if df.empty:
        return df

    # Add required columns
    df = df.copy()
    df["id"] = range(start_id, start_id + len(df))
    df["_source"] = "bi_pihps"
    df["_extracted_at"] = datetime.utcnow()

    # Ensure column order matches BigQuery schema
    columns = [
        "id", "tanggal", "comcat_id", "komoditas_nama", "pasar_tipe",
        "provinsi_id", "provinsi_nama", "kota_id", "kota_nama",
        "pasar_nama", "harga", "satuan", "_extracted_at", "_source",
    ]

    # Only keep columns that exist
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # Fix dtypes
    df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.date
    df["id"] = df["id"].astype("Int64")

    int_cols = ["pasar_tipe", "provinsi_id", "kota_id"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    float_cols = ["harga"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def main():
    parser = argparse.ArgumentParser(description="Load historical PIHPS data to BigQuery")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument(
        "--provinces", type=int, nargs="+", default=None,
        help="Province IDs to load (default: all TARGET_PROVINCE_IDS)",
    )
    args = parser.parse_args()

    # Determine which provinces to load
    province_ids = args.provinces or TARGET_PROVINCE_IDS

    # Init BigQuery client
    client = _get_bq_client()

    # Get next available ID for auto-increment
    current_id = _get_next_id(client, BQ_TABLE_HARGA)
    logger.info(f"Starting ID: {current_id}")

    # Build batch list: (year, prov_id)
    start_year = args.start_year
    batches = []
    for year in range(start_year, args.end_year + 1):
        for prov_id in province_ids:
            batches.append((year, prov_id))

    total_batches = len(batches)
    total_inserted = 0
    t_start = time.time()

    logger.info(f"Total batches: {total_batches} (year x province)")
    logger.info(f"Years: {start_year}-{args.end_year}")
    logger.info(f"Provinces: {province_ids}")
    logger.info(f"Target: BigQuery {BQ_TABLE_HARGA}")
    print()

    # Process per-province per-year
    with PihpsExtractor() as extractor:
        for i, (year, prov_id) in enumerate(batches, 1):
            batch_label = f"[{i}/{total_batches}] Year={year} Prov={prov_id}"

            try:
                df = _extract_prov_year(extractor, prov_id, year)

                if not df.empty:
                    # Prepare DataFrame with proper dtypes and IDs
                    df = _prepare_dataframe(df, current_id)
                    n = _load_to_bigquery(client, df, BQ_TABLE_HARGA)
                    current_id += len(df)
                    total_inserted += n
                    elapsed = time.time() - t_start
                    rate = total_inserted / elapsed if elapsed > 0 else 0
                    logger.success(
                        f"{batch_label}: {n:,} rows loaded "
                        f"(total: {total_inserted:,}, "
                        f"{rate:.0f} rows/sec, "
                        f"elapsed: {elapsed/60:.1f}min)"
                    )
                else:
                    logger.warning(f"{batch_label}: no data")

                # Log success checkpoint
                _log_pipeline_run(
                    client,
                    run_id=f"hist_{year}_{prov_id}",
                    pipeline_name="historical_load",
                    tanggal_mulai=date(year, 1, 1),
                    tanggal_selesai=min(date(year, 12, 31), date.today()),
                    records_inserted=len(df) if not df.empty else 0,
                    status="success",
                )

            except Exception as e:
                logger.error(f"{batch_label}: FAILED - {e}")
                _log_pipeline_run(
                    client,
                    run_id=f"hist_{year}_{prov_id}",
                    pipeline_name="historical_load",
                    tanggal_mulai=date(year, 1, 1),
                    tanggal_selesai=date(year, 12, 31),
                    records_inserted=0,
                    status="failed",
                    error_message=str(e)[:500],
                )
                continue

    elapsed_total = time.time() - t_start

    # Final summary
    print()
    print("=" * 60)
    print("HISTORICAL LOAD COMPLETE")
    print("=" * 60)
    print(f"  Target:         BigQuery {BQ_TABLE_HARGA}")
    print(f"  Years:          {start_year}-{args.end_year}")
    print(f"  Total loaded:   {total_inserted:,} rows")
    print(f"  Duration:       {elapsed_total/60:.1f} minutes")
    if elapsed_total > 0:
        print(f"  Avg rate:       {total_inserted/elapsed_total:.0f} rows/sec")
    print("=" * 60)


if __name__ == "__main__":
    main()

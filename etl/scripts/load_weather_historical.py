"""
Load historical weather data from Open-Meteo into BigQuery raw.cuaca_harian.

Open-Meteo supports wide date ranges per request, so this is fast:
- 5 locations x 6 years = ~5 API calls = ~3 minutes total.
- Load via BigQuery batch load (FREE).

Usage:
    cd bi-hackathon-group-1
    python etl/scripts/load_weather_historical.py
    python etl/scripts/load_weather_historical.py --start-year 2024
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime

# Ensure etl/ is in path for relative imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load credentials from .envs/.env
from dotenv import load_dotenv
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, ".envs", ".env"))

import pandas as pd
from google.cloud import bigquery
from loguru import logger

from config.constants import WEATHER_LOCATIONS
from config.log_config import setup_logging
from extractors.openmeteo_extractor import OpenMeteoExtractor


# -- Config --------------------------------------------------------------------

DEFAULT_START_YEAR = 2020
DEFAULT_END_YEAR = 2026

GCP_PROJECT = os.getenv("GCP_PROJECT", "radar-pangan-hackathon")
BQ_LOCATION = os.getenv("BQ_LOCATION", "asia-southeast2")
BQ_TABLE = f"{GCP_PROJECT}.raw.cuaca_harian"


def _get_bq_client() -> bigquery.Client:
    """Create BigQuery client with project config."""
    return bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)


def _get_next_id(client: bigquery.Client) -> int:
    """Get next available ID for cuaca_harian table."""
    query = f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{BQ_TABLE}` WHERE tanggal >= '2020-01-01'"
    result = client.query(query).result()
    row = next(iter(result))
    return row[0]


def _prepare_dataframe(df: pd.DataFrame, start_id: int) -> pd.DataFrame:
    """Prepare DataFrame for BigQuery load with proper dtypes."""
    if df.empty:
        return df

    df = df.copy()

    # Add required columns
    df["id"] = range(start_id, start_id + len(df))
    df["_source"] = "open_meteo"
    df["_extracted_at"] = datetime.utcnow()

    # Ensure column order matches BigQuery schema
    columns = [
        "id", "tanggal", "lokasi_label", "provinsi_id", "latitude", "longitude",
        "precipitation_sum", "rain_sum", "temperature_max", "temperature_min",
        "wind_speed_max", "et0_evapotranspiration", "sunshine_duration",
        "_extracted_at", "_source",
    ]

    # Only keep columns that exist
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # Fix dtypes
    df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.date
    df["id"] = df["id"].astype("Int64")
    df["provinsi_id"] = pd.to_numeric(df["provinsi_id"], errors="coerce").astype("Int64")

    float_cols = [
        "latitude", "longitude", "precipitation_sum", "rain_sum",
        "temperature_max", "temperature_min", "wind_speed_max",
        "et0_evapotranspiration", "sunshine_duration",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with null REQUIRED fields (BQ rejects nulls on REQUIRED columns)
    required_cols = ["tanggal", "lokasi_label", "provinsi_id", "latitude", "longitude"]
    existing_required = [c for c in required_cols if c in df.columns]
    before = len(df)
    df = df.dropna(subset=existing_required)
    dropped = before - len(df)
    if dropped > 0:
        logger.warning(f"Dropped {dropped} rows with null required fields")

    # Re-assign sequential IDs after dropping rows
    df["id"] = range(start_id, start_id + len(df))

    return df


def main():
    parser = argparse.ArgumentParser(description="Load historical weather data from Open-Meteo to BigQuery")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    args = parser.parse_args()

    # Init BigQuery client
    client = _get_bq_client()

    t_start = time.time()
    start_date = date(args.start_year, 1, 1)
    end_date = min(date(args.end_year, 12, 31), date.today())

    logger.info(f"Loading weather data: {start_date} to {end_date}")
    logger.info(f"Locations: {sum(len(v) for v in WEATHER_LOCATIONS.values())} points "
                f"across {len(WEATHER_LOCATIONS)} provinces")
    logger.info(f"Target: BigQuery {BQ_TABLE}")

    # Extract from Open-Meteo
    with OpenMeteoExtractor(request_delay=0.5) as extractor:
        df = extractor.extract_all_locations(
            start_date=start_date,
            end_date=end_date,
            locations=WEATHER_LOCATIONS,
        )

    if df.empty:
        logger.warning("No weather data extracted!")
        return

    logger.info(f"Extracted {len(df):,} weather records. Loading into BigQuery...")

    # Get next available ID
    next_id = _get_next_id(client)

    # Prepare DataFrame for BigQuery
    df = _prepare_dataframe(df, next_id)

    # Load to BigQuery (batch load = FREE)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    load_job = client.load_table_from_dataframe(
        df, BQ_TABLE, job_config=job_config,
    )
    load_job.result()  # Wait for completion

    elapsed = time.time() - t_start
    n_loaded = load_job.output_rows

    logger.success(f"Loaded {n_loaded:,} weather records to BigQuery")

    # Summary
    print()
    print("=" * 60)
    print("WEATHER DATA LOAD COMPLETE")
    print("=" * 60)
    print(f"  Target:      BigQuery {BQ_TABLE}")
    print(f"  Period:      {start_date} to {end_date}")
    print(f"  Locations:   {sum(len(v) for v in WEATHER_LOCATIONS.values())}")
    print(f"  Records:     {n_loaded:,}")
    print(f"  Duration:    {elapsed:.1f} seconds")
    print("=" * 60)


if __name__ == "__main__":
    setup_logging()
    main()

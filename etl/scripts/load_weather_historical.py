"""
Load historical weather data from Open-Meteo into raw.cuaca_harian.

Open-Meteo supports wide date ranges per request, so this is fast:
- 5 locations × 6 years = ~5 API calls = ~3 minutes total.
- Estimated DB size: ~5-10 MB (very small compared to PIHPS data).

Usage:
    cd etl
    python -X utf8 scripts/load_weather_historical.py
    python -X utf8 scripts/load_weather_historical.py --start-year 2024  # recent only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load Supabase credentials from .envs/.env
from dotenv import load_dotenv
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, ".envs", ".env"))

import psycopg2
import psycopg2.extras
from loguru import logger

from config.constants import WEATHER_LOCATIONS
from extractors.openmeteo_extractor import OpenMeteoExtractor
from loaders.postgres_loader import PostgresLoader, _get_dsn


DEFAULT_START_YEAR = 2020
DEFAULT_END_YEAR = 2026

UPSERT_SQL = """
    INSERT INTO raw.cuaca_harian
        (tanggal, lokasi_label, provinsi_id, latitude, longitude,
         precipitation_sum, rain_sum, temperature_max, temperature_min,
         wind_speed_max, et0_evapotranspiration, sunshine_duration)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (tanggal, latitude, longitude) DO UPDATE SET
        precipitation_sum     = EXCLUDED.precipitation_sum,
        rain_sum              = EXCLUDED.rain_sum,
        temperature_max       = EXCLUDED.temperature_max,
        temperature_min       = EXCLUDED.temperature_min,
        wind_speed_max        = EXCLUDED.wind_speed_max,
        et0_evapotranspiration = EXCLUDED.et0_evapotranspiration,
        sunshine_duration     = EXCLUDED.sunshine_duration,
        _extracted_at         = CURRENT_TIMESTAMP
"""


def main():
    parser = argparse.ArgumentParser(description="Load historical weather data from Open-Meteo")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    args = parser.parse_args()

    # Ensure schema + table exist
    with PostgresLoader() as loader:
        loader.init_schema()

    # Connect to database
    conn = psycopg2.connect(_get_dsn())

    t_start = time.time()
    start_date = date(args.start_year, 1, 1)
    end_date = min(date(args.end_year, 12, 31), date.today())

    logger.info(f"Loading weather data: {start_date} → {end_date}")
    logger.info(f"Locations: {sum(len(v) for v in WEATHER_LOCATIONS.values())} points "
                f"across {len(WEATHER_LOCATIONS)} provinces")

    # Extract from Open-Meteo
    with OpenMeteoExtractor(request_delay=0.5) as extractor:
        df = extractor.extract_all_locations(
            start_date=start_date,
            end_date=end_date,
            locations=WEATHER_LOCATIONS,
        )

    if df.empty:
        logger.warning("No weather data extracted!")
        conn.close()
        return

    logger.info(f"Extracted {len(df):,} weather records. Inserting into DB...")

    # Bulk upsert into raw.cuaca_harian
    cur = conn.cursor()
    records = []
    for _, row in df.iterrows():
        records.append((
            row["tanggal"],
            row["lokasi_label"],
            row["provinsi_id"],
            row["latitude"],
            row["longitude"],
            row.get("precipitation_sum"),
            row.get("rain_sum"),
            row.get("temperature_max"),
            row.get("temperature_min"),
            row.get("wind_speed_max"),
            row.get("et0_evapotranspiration"),
            row.get("sunshine_duration"),
        ))

    try:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, records, page_size=500)
        conn.commit()
        logger.success(f"Inserted/updated {len(records):,} weather records")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to insert weather data: {e}")
        raise
    finally:
        cur.close()

    elapsed = time.time() - t_start
    conn.close()

    # Summary
    print()
    print("=" * 60)
    print("WEATHER DATA LOAD COMPLETE")
    print("=" * 60)
    print(f"  Period:      {start_date} to {end_date}")
    print(f"  Locations:   {sum(len(v) for v in WEATHER_LOCATIONS.values())}")
    print(f"  Records:     {len(records):,}")
    print(f"  Duration:    {elapsed:.1f} seconds")
    print("=" * 60)


if __name__ == "__main__":
    main()

"""
Fetch 3-day BMKG weather forecast and store to Supabase app.bmkg_siaga.

This script complements the historical BMKG siaga derived from Open-Meteo.
It fetches real-time forecast from BMKG public API for the next 3 days
and UPSERTS into app.bmkg_siaga with sumber='bmkg_forecast'.

Historical data (sumber='derived_openmeteo') is NOT overwritten.
Only future-dated rows are inserted/updated.

Usage:
    uv run python etl/scripts/fetch_bmkg_forecast.py

Runs in Kestra daily pipeline after cuaca extraction.
"""
from __future__ import annotations

import os
import sys
from datetime import date

from loguru import logger

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Load env vars before any imports that need them
def _load_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".envs", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

from etl.config.log_config import setup_logging
from src.data.database import init_pool, close_pool, db_cursor
from etl.extractors.bmkg_extractor import BmkgExtractor


def fetch_and_store() -> int:
    """
    Fetch BMKG 3-day forecast for MVP cities and store to app.bmkg_siaga.

    Only inserts/updates rows with sumber='bmkg_forecast'.
    Historical rows (sumber='derived_openmeteo') are not touched.

    Returns:
        Number of forecast rows upserted.
    """
    logger.info("Fetching BMKG 3-day forecast for MVP cities...")

    with BmkgExtractor() as extractor:
        all_results = extractor.extract_all_cities()

        if not all_results:
            logger.warning("No forecast data from BMKG API")
            return 0

        # Prepare rows for upsert
        rows: list[tuple] = []
        for city_name, forecasts in all_results.items():
            for f in forecasts:
                if not f.get("tanggal"):
                    continue

                precip = f.get("total_precip", 0)
                wind = f.get("max_wind", 0)
                level, level_label, fenomena = extractor.derive_siaga_level(precip, wind)

                provinsi_id = f.get("provinsi_id", 0)
                provinsi_nama = f.get("lokasi", city_name)

                rows.append((
                    f["tanggal"],
                    provinsi_id,
                    provinsi_nama,
                    level,
                    level_label,
                    fenomena,
                    "bmkg_forecast",
                ))

    if not rows:
        logger.warning("No forecast rows to upsert")
        return 0

    logger.info(f"Upserting {len(rows)} forecast rows to app.bmkg_siaga...")

    # Delete existing forecast rows (sumber='bmkg_forecast') then insert fresh
    # This avoids stale forecasts accumulating
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM app.bmkg_siaga WHERE sumber = 'bmkg_forecast'"
        )
        deleted = cur.rowcount
        if deleted:
            logger.info(f"Cleared {deleted} old forecast rows")

        # Batch insert
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values_list = []
            params: list = []
            for row in batch:
                values_list.append("(%s, %s, %s, %s, %s, %s, %s)")
                params.extend(row)

            sql = f"""
                INSERT INTO app.bmkg_siaga
                    (tanggal, provinsi_id, provinsi_nama,
                     level, level_label, fenomena, sumber)
                VALUES {', '.join(values_list)}
            """
            cur.execute(sql, params)

    logger.success(f"Upserted {len(rows)} BMKG forecast rows to app.bmkg_siaga")

    # Log summary per level
    level_counts: dict[str, int] = {}
    for r in rows:
        lbl = r[4]
        level_counts[lbl] = level_counts.get(lbl, 0) + 1
    for lbl, cnt in sorted(level_counts.items()):
        logger.info(f"  {lbl}: {cnt} forecast records")

    return len(rows)


def main() -> None:
    logger.info("=" * 50)
    logger.info("BMKG Forecast -> Supabase app.bmkg_siaga")
    logger.info("=" * 50)

    # Init Supabase connection
    init_pool()

    try:
        count = fetch_and_store()
        logger.success(f"Done: {count} forecast rows stored")
    except Exception as e:
        logger.error(f"BMKG forecast fetch failed: {e}")
        raise
    finally:
        close_pool()


if __name__ == "__main__":
    setup_logging()
    main()

"""
Sync Gold layer data: BigQuery (Bronze/Silver) -> Supabase PostgreSQL (Gold).

This script copies the data that the app needs from BigQuery into Supabase PostgreSQL,
so the FastAPI app can serve all user requests from Supabase (low-latency)
instead of hitting BigQuery on every request.

Tables synced:
  - app.harga_pangan    <- from raw.harga_pangan (filtered to MVP komoditas, pasar tradisional)
  - app.cuaca_harian    <- from raw.cuaca_harian
  - app.hari_besar      <- from raw.hari_besar
  - app.bmkg_siaga      <- derived from app.cuaca_harian (precipitation/wind thresholds)
  - app.stok_bapanas    <- dummy data (no real source yet)

Usage:
  # Requires both GCP ADC and Supabase credentials
  uv run python etl/scripts/sync_gold_to_postgres.py

  # Sync only specific tables
  uv run python etl/scripts/sync_gold_to_postgres.py --tables harga_pangan
  uv run python etl/scripts/sync_gold_to_postgres.py --tables cuaca_harian,hari_besar
  uv run python etl/scripts/sync_gold_to_postgres.py --tables bmkg_siaga,stok_bapanas
"""
from __future__ import annotations

import argparse
import os
import sys
import time

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

from src.data.bigquery_client import bq_query, get_bq_client, close_bq_client
from src.data.database import init_pool, close_pool, db_cursor


# -- DDL: Create tables in Supabase if not exist --------------------------------

DDL_HARGA_PANGAN = """
CREATE TABLE IF NOT EXISTS app.harga_pangan (
    id              SERIAL PRIMARY KEY,
    tanggal         DATE NOT NULL,
    comcat_id       VARCHAR NOT NULL,
    komoditas_nama  VARCHAR NOT NULL,
    pasar_tipe      INTEGER NOT NULL DEFAULT 1,
    provinsi_id     INTEGER NOT NULL,
    provinsi_nama   VARCHAR NOT NULL,
    kota_id         INTEGER NOT NULL,
    kota_nama       VARCHAR NOT NULL,
    harga           DOUBLE PRECISION NOT NULL,
    satuan          VARCHAR NOT NULL DEFAULT 'kg'
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_harga_comcat_tanggal
    ON app.harga_pangan (comcat_id, tanggal DESC);
CREATE INDEX IF NOT EXISTS idx_harga_tanggal
    ON app.harga_pangan (tanggal DESC);
CREATE INDEX IF NOT EXISTS idx_harga_comcat_pasar_tanggal
    ON app.harga_pangan (comcat_id, pasar_tipe, tanggal DESC);
"""

DDL_CUACA_HARIAN = """
CREATE TABLE IF NOT EXISTS app.cuaca_harian (
    id                      SERIAL PRIMARY KEY,
    tanggal                 DATE NOT NULL,
    lokasi_label            VARCHAR NOT NULL,
    provinsi_id             INTEGER NOT NULL,
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    precipitation_sum       DOUBLE PRECISION,
    rain_sum                DOUBLE PRECISION,
    temperature_max         DOUBLE PRECISION,
    temperature_min         DOUBLE PRECISION,
    wind_speed_max          DOUBLE PRECISION,
    et0_evapotranspiration  DOUBLE PRECISION,
    sunshine_duration       DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_cuaca_prov_tanggal
    ON app.cuaca_harian (provinsi_id, tanggal DESC);
"""

DDL_HARI_BESAR = """
CREATE TABLE IF NOT EXISTS app.hari_besar (
    id        SERIAL PRIMARY KEY,
    tanggal   DATE NOT NULL,
    nama      VARCHAR NOT NULL,
    kategori  VARCHAR NOT NULL,
    tahun     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hari_besar_tanggal
    ON app.hari_besar (tanggal);
"""

# BMKG Siaga - derived from cuaca_harian using precipitation/wind thresholds.
# Maps Open-Meteo historical data to BMKG-style warning levels.
DDL_BMKG_SIAGA = """
CREATE TABLE IF NOT EXISTS app.bmkg_siaga (
    id              SERIAL PRIMARY KEY,
    tanggal         DATE NOT NULL,
    provinsi_id     INTEGER NOT NULL,
    provinsi_nama   VARCHAR,
    level           INTEGER NOT NULL DEFAULT 1,
    level_label     VARCHAR NOT NULL DEFAULT 'Normal',
    fenomena        VARCHAR,
    sumber          VARCHAR NOT NULL DEFAULT 'derived_openmeteo'
);

CREATE INDEX IF NOT EXISTS idx_bmkg_siaga_prov_tanggal
    ON app.bmkg_siaga (provinsi_id, tanggal DESC);
CREATE INDEX IF NOT EXISTS idx_bmkg_siaga_tanggal
    ON app.bmkg_siaga (tanggal DESC);
"""

# Stok Bapanas - dummy data for ML Threat 4 evaluation.
# Real data from Bapanas not available yet.
DDL_STOK_BAPANAS = """
CREATE TABLE IF NOT EXISTS app.stok_bapanas (
    id              SERIAL PRIMARY KEY,
    tanggal         DATE NOT NULL,
    komoditas_id    VARCHAR NOT NULL,
    komoditas_nama  VARCHAR,
    stok_ton        NUMERIC,
    kebutuhan_ton   NUMERIC,
    rasio_stok      NUMERIC,
    sumber          VARCHAR NOT NULL DEFAULT 'dummy'
);

CREATE INDEX IF NOT EXISTS idx_stok_komoditas_tanggal
    ON app.stok_bapanas (komoditas_id, tanggal DESC);
"""


def _create_tables() -> None:
    """Create Gold layer tables in Supabase if they don't exist."""
    logger.info("Creating tables in Supabase (if not exist)...")
    with db_cursor() as cur:
        cur.execute(DDL_HARGA_PANGAN)
        cur.execute(DDL_CUACA_HARIAN)
        cur.execute(DDL_HARI_BESAR)
        cur.execute(DDL_BMKG_SIAGA)
        cur.execute(DDL_STOK_BAPANAS)
    logger.success("Tables created/verified")


# -- Sync functions -------------------------------------------------------------

# MVP komoditas filter
MVP_COMCAT_IDS = [
    "com_11", "com_12", "com_13", "com_14", "com_15", "com_16"
]


def sync_harga_pangan() -> int:
    """Sync harga_pangan from BigQuery -> Supabase. Returns row count."""
    logger.info("Syncing app.harga_pangan...")

    # Fetch from BigQuery (filtered to MVP komoditas, pasar tradisional only)
    comcat_filter = ", ".join(f"'{c}'" for c in MVP_COMCAT_IDS)
    rows = bq_query(f"""
        SELECT
            tanggal, comcat_id, komoditas_nama, pasar_tipe,
            provinsi_id, provinsi_nama, kota_id, kota_nama,
            harga, satuan
        FROM `raw.harga_pangan`
        WHERE tanggal >= '2020-01-01'
          AND comcat_id IN ({comcat_filter})
          AND pasar_tipe = 1
          AND harga > 0
        ORDER BY tanggal, comcat_id, kota_id
    """)

    if not rows:
        logger.error("No data returned from BigQuery for harga_pangan")
        return 0

    logger.info(f"Fetched {len(rows)} rows from BigQuery")

    # Truncate + insert into Supabase (full refresh)
    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.harga_pangan RESTART IDENTITY")

        # Batch insert (1000 rows at a time)
        batch_size = 1000
        inserted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values_list = []
            params = []
            for row in batch:
                values_list.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
                params.extend([
                    row["tanggal"], row["comcat_id"], row["komoditas_nama"],
                    row["pasar_tipe"], row["provinsi_id"], row["provinsi_nama"],
                    row["kota_id"], row["kota_nama"], row["harga"], row["satuan"],
                ])

            sql = f"""
                INSERT INTO app.harga_pangan
                    (tanggal, comcat_id, komoditas_nama, pasar_tipe,
                     provinsi_id, provinsi_nama, kota_id, kota_nama, harga, satuan)
                VALUES {', '.join(values_list)}
            """
            cur.execute(sql, params)
            inserted += len(batch)

    logger.success(f"Synced {len(rows)} rows to app.harga_pangan")
    return len(rows)


def sync_cuaca_harian() -> int:
    """Sync cuaca_harian from BigQuery -> Supabase. Returns row count."""
    logger.info("Syncing app.cuaca_harian...")

    rows = bq_query("""
        SELECT
            tanggal, lokasi_label, provinsi_id, latitude, longitude,
            precipitation_sum, rain_sum, temperature_max, temperature_min,
            wind_speed_max, et0_evapotranspiration, sunshine_duration
        FROM `raw.cuaca_harian`
        ORDER BY tanggal, provinsi_id
    """)

    if not rows:
        logger.error("No data returned from BigQuery for cuaca_harian")
        return 0

    logger.info(f"Fetched {len(rows)} rows from BigQuery")

    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.cuaca_harian RESTART IDENTITY")

        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values_list = []
            params = []
            for row in batch:
                values_list.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
                params.extend([
                    row["tanggal"], row["lokasi_label"], row["provinsi_id"],
                    row["latitude"], row["longitude"],
                    row["precipitation_sum"], row["rain_sum"],
                    row["temperature_max"], row["temperature_min"],
                    row["wind_speed_max"], row["et0_evapotranspiration"],
                    row["sunshine_duration"],
                ])

            sql = f"""
                INSERT INTO app.cuaca_harian
                    (tanggal, lokasi_label, provinsi_id, latitude, longitude,
                     precipitation_sum, rain_sum, temperature_max, temperature_min,
                     wind_speed_max, et0_evapotranspiration, sunshine_duration)
                VALUES {', '.join(values_list)}
            """
            cur.execute(sql, params)

    logger.success(f"Synced {len(rows)} rows to app.cuaca_harian")
    return len(rows)


def sync_hari_besar() -> int:
    """Sync hari_besar from BigQuery -> Supabase. Returns row count."""
    logger.info("Syncing app.hari_besar...")

    rows = bq_query("""
        SELECT tanggal, nama, kategori, tahun
        FROM `raw.hari_besar`
        ORDER BY tanggal
    """)

    if not rows:
        logger.error("No data returned from BigQuery for hari_besar")
        return 0

    logger.info(f"Fetched {len(rows)} rows from BigQuery")

    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.hari_besar RESTART IDENTITY")

        for row in rows:
            cur.execute("""
                INSERT INTO app.hari_besar (tanggal, nama, kategori, tahun)
                VALUES (%s, %s, %s, %s)
            """, (row["tanggal"], row["nama"], row["kategori"], row["tahun"]))

    logger.success(f"Synced {len(rows)} rows to app.hari_besar")
    return len(rows)


# Province ID to name mapping (same as etl/config/constants.py)
_PROVINCE_NAMES = {11: "Banten", 12: "Jawa Barat", 13: "DKI Jakarta", 26: "Sulawesi Selatan"}


def sync_bmkg_siaga() -> int:
    """
    Derive BMKG-style warning levels from cuaca_harian data in Supabase.

    Derives warning levels from Open-Meteo historical weather data using
    precipitation and wind speed thresholds. This creates a historical
    BMKG siaga table that ML can use for Threat 3 evaluation.

    Thresholds (based on BMKG classification):
      Level 1 (Normal/Hijau)  : precip < 50mm AND wind < 40km/h
      Level 2 (Waspada/Kuning): precip 50-100mm OR wind 40-60km/h
      Level 3 (Siaga/Oranye)  : precip 100-150mm OR wind 60-80km/h
      Level 4 (Awas/Merah)    : precip >= 150mm OR wind >= 80km/h
    """
    logger.info("Syncing app.bmkg_siaga (derived from app.cuaca_harian)...")

    # Read cuaca_harian from Supabase (already synced), aggregate per province per day
    with db_cursor() as cur:
        cur.execute("""
            SELECT
                tanggal,
                provinsi_id,
                MAX(precipitation_sum) AS max_precip,
                MAX(rain_sum) AS max_rain,
                MAX(wind_speed_max) AS max_wind,
                MAX(temperature_max) AS max_temp
            FROM app.cuaca_harian
            GROUP BY tanggal, provinsi_id
            ORDER BY tanggal, provinsi_id
        """)
        weather_rows = cur.fetchall()

    if not weather_rows:
        logger.warning("No cuaca_harian data found - sync cuaca_harian first")
        return 0

    logger.info(f"Found {len(weather_rows)} (date, province) records to classify")

    # Derive warning levels
    siaga_rows: list[tuple] = []
    for row in weather_rows:
        tanggal = row[0]
        provinsi_id = row[1]
        precip = float(row[2] or 0)
        rain = float(row[3] or 0)
        wind = float(row[4] or 0)
        temp = float(row[5] or 0)

        # Use max of precip and rain for threshold
        total_precip = max(precip, rain)

        # Classify warning level
        level = 1
        level_label = "Normal"
        fenomena = "Cuaca normal"

        if total_precip >= 150 or wind >= 80:
            level = 4
            level_label = "Awas"
            if total_precip >= 150:
                fenomena = f"Hujan Sangat Lebat ({total_precip:.0f}mm)"
            else:
                fenomena = f"Angin Sangat Kencang ({wind:.0f}km/h)"
        elif total_precip >= 100 or wind >= 60:
            level = 3
            level_label = "Siaga"
            if total_precip >= 100:
                fenomena = f"Hujan Lebat ({total_precip:.0f}mm)"
            else:
                fenomena = f"Angin Kencang ({wind:.0f}km/h)"
        elif total_precip >= 50 or wind >= 40:
            level = 2
            level_label = "Waspada"
            if total_precip >= 50:
                fenomena = f"Hujan Sedang ({total_precip:.0f}mm)"
            else:
                fenomena = f"Angin Sedang ({wind:.0f}km/h)"

        # Also check drought (no rain for extended periods is not per-row,
        # but high temp + zero precip is a signal)
        if total_precip == 0 and temp >= 38:
            if level < 2:
                level = 2
                level_label = "Waspada"
                fenomena = f"Potensi Kekeringan (suhu {temp:.0f}C, tanpa hujan)"

        provinsi_nama = _PROVINCE_NAMES.get(provinsi_id, f"Provinsi {provinsi_id}")

        siaga_rows.append((
            tanggal, provinsi_id, provinsi_nama,
            level, level_label, fenomena, "derived_openmeteo",
        ))

    # Write to Supabase
    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.bmkg_siaga RESTART IDENTITY")

        batch_size = 1000
        for i in range(0, len(siaga_rows), batch_size):
            batch = siaga_rows[i:i + batch_size]
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

    logger.success(f"Synced {len(siaga_rows)} rows to app.bmkg_siaga")

    # Log summary stats per warning level
    level_counts: dict[str, int] = {}
    for r in siaga_rows:
        lbl = r[4]  # level_label
        level_counts[lbl] = level_counts.get(lbl, 0) + 1
    for lbl, cnt in sorted(level_counts.items()):
        logger.info(f"  {lbl}: {cnt} records")

    return len(siaga_rows)


def sync_stok_bapanas() -> int:
    """
    Seed dummy data for app.stok_bapanas.

    Real stock data from Bapanas is not available. This generates realistic
    dummy data with seasonal patterns for ML Threat 4 evaluation.

    Patterns:
      - Base rasio_stok ~1.3 (normal supply buffer)
      - Dips around Ramadan/Lebaran (month 3-4) to ~0.8-1.0
      - Slight surplus post-harvest (month 7-9) at ~1.5-1.8
      - Random noise for realism
    """
    import random
    from datetime import date, timedelta

    logger.info("Syncing app.stok_bapanas (dummy data)...")

    komoditas = [
        ("com_11", "Bawang Merah", 80),
        ("com_12", "Bawang Putih", 60),
        ("com_13", "Cabai Merah Besar", 40),
        ("com_14", "Cabai Merah Keriting", 35),
        ("com_15", "Cabai Rawit Hijau", 25),
        ("com_16", "Cabai Rawit Merah", 30),
    ]

    random.seed(42)  # Reproducible dummy data

    rows: list[tuple] = []
    start_date = date(2024, 1, 1)
    end_date = date(2026, 5, 31)

    current = start_date
    while current <= end_date:
        month = current.month
        for kom_id, kom_nama, base_kebutuhan in komoditas:
            # Seasonal adjustment for rasio_stok
            if month in (3, 4):
                # Ramadan/Lebaran: demand spike, stock dips
                base_rasio = 0.85 + random.uniform(-0.15, 0.15)
            elif month in (7, 8, 9):
                # Post-harvest: surplus
                base_rasio = 1.6 + random.uniform(-0.2, 0.2)
            elif month == 12:
                # Year-end: slight pressure
                base_rasio = 1.1 + random.uniform(-0.1, 0.15)
            else:
                # Normal
                base_rasio = 1.3 + random.uniform(-0.2, 0.2)

            # Ensure non-negative
            rasio = max(0.3, base_rasio)
            kebutuhan = base_kebutuhan + random.uniform(-5, 5)
            stok = kebutuhan * rasio

            rows.append((
                current, kom_id, kom_nama,
                round(stok, 1), round(kebutuhan, 1), round(rasio, 3),
                "dummy",
            ))

        # Weekly data (every 7 days) to keep table manageable
        current += timedelta(days=7)

    logger.info(f"Generated {len(rows)} dummy stock records")

    # Write to Supabase
    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.stok_bapanas RESTART IDENTITY")

        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values_list = []
            params: list = []
            for row in batch:
                values_list.append("(%s, %s, %s, %s, %s, %s, %s)")
                params.extend(row)

            sql = f"""
                INSERT INTO app.stok_bapanas
                    (tanggal, komoditas_id, komoditas_nama,
                     stok_ton, kebutuhan_ton, rasio_stok, sumber)
                VALUES {', '.join(values_list)}
            """
            cur.execute(sql, params)

    logger.success(f"Seeded {len(rows)} rows to app.stok_bapanas")
    return len(rows)


# -- Main ----------------------------------------------------------------------

SYNC_FUNCTIONS = {
    "harga_pangan": sync_harga_pangan,
    "cuaca_harian": sync_cuaca_harian,
    "hari_besar": sync_hari_besar,
    "bmkg_siaga": sync_bmkg_siaga,
    "stok_bapanas": sync_stok_bapanas,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Gold layer: BigQuery -> Supabase PostgreSQL")
    parser.add_argument(
        "--tables",
        type=str,
        default=None,
        help=(
            "Comma-separated table names to sync (default: all). "
            "Options: harga_pangan, cuaca_harian, hari_besar, bmkg_siaga, stok_bapanas"
        ),
    )
    args = parser.parse_args()

    # Determine which tables to sync
    if args.tables:
        table_names = [t.strip() for t in args.tables.split(",")]
        for name in table_names:
            if name not in SYNC_FUNCTIONS:
                logger.error(f"Unknown table: {name}. Options: {', '.join(SYNC_FUNCTIONS.keys())}")
                sys.exit(1)
    else:
        table_names = list(SYNC_FUNCTIONS.keys())

    logger.info("=" * 60)
    logger.info("Gold Layer Sync: BigQuery -> Supabase PostgreSQL")
    logger.info(f"Tables: {', '.join(table_names)}")
    logger.info("=" * 60)

    start_time = time.time()

    # Initialize connections
    get_bq_client()
    init_pool()

    # Create tables if needed
    _create_tables()

    # Sync each table
    total_rows = 0
    for name in table_names:
        try:
            count = SYNC_FUNCTIONS[name]()
            total_rows += count
        except Exception as e:
            logger.error(f"Error syncing {name}: {e}")
            raise

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.success(f"Sync complete: {total_rows} total rows in {elapsed:.1f}s")
    logger.info("=" * 60)

    # Cleanup
    close_bq_client()
    close_pool()


if __name__ == "__main__":
    main()

"""
Sync Gold layer data: BigQuery (Bronze/Silver) -> Supabase PostgreSQL (Gold).

This script copies the data that the app needs from BigQuery into Supabase PostgreSQL,
so the FastAPI app can serve all user requests from Supabase (low-latency)
instead of hitting BigQuery on every request.

Tables synced:
  - app.harga_pangan    <- from raw.harga_pangan (filtered to MVP komoditas, pasar tradisional)
  - app.cuaca_harian    <- from raw.cuaca_harian
  - app.hari_besar      <- from raw.hari_besar

Usage:
  # Requires both GCP ADC and Supabase credentials
  uv run python etl/scripts/sync_gold_to_postgres.py

  # Sync only specific tables
  uv run python etl/scripts/sync_gold_to_postgres.py --tables harga_pangan
  uv run python etl/scripts/sync_gold_to_postgres.py --tables cuaca_harian,hari_besar
"""
from __future__ import annotations

import argparse
import os
import sys
import time

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


def _create_tables() -> None:
    """Create Gold layer tables in Supabase if they don't exist."""
    print("Creating tables in Supabase (if not exist)...")
    with db_cursor() as cur:
        cur.execute(DDL_HARGA_PANGAN)
        cur.execute(DDL_CUACA_HARIAN)
        cur.execute(DDL_HARI_BESAR)
    print("  [OK] Tables created/verified")


# -- Sync functions -------------------------------------------------------------

# MVP komoditas filter
MVP_COMCAT_IDS = [
    "com_11", "com_12", "com_13", "com_14", "com_15", "com_16"
]


def sync_harga_pangan() -> int:
    """Sync harga_pangan from BigQuery -> Supabase. Returns row count."""
    print("\nSyncing app.harga_pangan...")

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
        print("  [FAIL] No data returned from BigQuery")
        return 0

    print(f"  Fetched {len(rows)} rows from BigQuery")

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
            print(f"  Inserted {inserted}/{len(rows)} rows...", end="\r")

    print(f"\n  [OK] Synced {len(rows)} rows to app.harga_pangan")
    return len(rows)


def sync_cuaca_harian() -> int:
    """Sync cuaca_harian from BigQuery -> Supabase. Returns row count."""
    print("\nSyncing app.cuaca_harian...")

    rows = bq_query("""
        SELECT
            tanggal, lokasi_label, provinsi_id, latitude, longitude,
            precipitation_sum, rain_sum, temperature_max, temperature_min,
            wind_speed_max, et0_evapotranspiration, sunshine_duration
        FROM `raw.cuaca_harian`
        ORDER BY tanggal, provinsi_id
    """)

    if not rows:
        print("  [FAIL] No data returned from BigQuery")
        return 0

    print(f"  Fetched {len(rows)} rows from BigQuery")

    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.cuaca_harian RESTART IDENTITY")

        batch_size = 1000
        inserted = 0
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
            inserted += len(batch)

    print(f"  [OK] Synced {len(rows)} rows to app.cuaca_harian")
    return len(rows)


def sync_hari_besar() -> int:
    """Sync hari_besar from BigQuery -> Supabase. Returns row count."""
    print("\nSyncing app.hari_besar...")

    rows = bq_query("""
        SELECT tanggal, nama, kategori, tahun
        FROM `raw.hari_besar`
        ORDER BY tanggal
    """)

    if not rows:
        print("  [FAIL] No data returned from BigQuery")
        return 0

    print(f"  Fetched {len(rows)} rows from BigQuery")

    with db_cursor() as cur:
        cur.execute("TRUNCATE TABLE app.hari_besar RESTART IDENTITY")

        for row in rows:
            cur.execute("""
                INSERT INTO app.hari_besar (tanggal, nama, kategori, tahun)
                VALUES (%s, %s, %s, %s)
            """, (row["tanggal"], row["nama"], row["kategori"], row["tahun"]))

    print(f"  [OK] Synced {len(rows)} rows to app.hari_besar")
    return len(rows)


# -- Main ----------------------------------------------------------------------

SYNC_FUNCTIONS = {
    "harga_pangan": sync_harga_pangan,
    "cuaca_harian": sync_cuaca_harian,
    "hari_besar": sync_hari_besar,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Gold layer: BigQuery -> Supabase PostgreSQL")
    parser.add_argument(
        "--tables",
        type=str,
        default=None,
        help="Comma-separated table names to sync (default: all). Options: harga_pangan, cuaca_harian, hari_besar",
    )
    args = parser.parse_args()

    # Determine which tables to sync
    if args.tables:
        table_names = [t.strip() for t in args.tables.split(",")]
        for name in table_names:
            if name not in SYNC_FUNCTIONS:
                print(f"Unknown table: {name}. Options: {', '.join(SYNC_FUNCTIONS.keys())}")
                sys.exit(1)
    else:
        table_names = list(SYNC_FUNCTIONS.keys())

    print("=" * 60)
    print("Gold Layer Sync: BigQuery -> Supabase PostgreSQL")
    print(f"Tables: {', '.join(table_names)}")
    print("=" * 60)

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
            print(f"\n  [FAIL] Error syncing {name}: {e}")
            raise

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"Sync complete: {total_rows} total rows in {elapsed:.1f}s")
    print("=" * 60)

    # Cleanup
    close_bq_client()
    close_pool()


if __name__ == "__main__":
    main()

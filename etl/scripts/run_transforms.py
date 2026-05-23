"""
run_transforms.py — Jalankan transformasi staging + mart langsung di DuckDB tanpa dbt CLI.

Digunakan sebagai pengganti dbt karena dbt-dbt tidak kompatibel dengan Python 3.14.
SQL identik dengan model dbt asli, tinggal substitusi ref() dan source() dengan nama tabel aktual.
"""
import sys
import os
from pathlib import Path

# Setup path
ETL_DIR = Path(__file__).parent.parent.resolve()
REPO_DIR = ETL_DIR.parent
sys.path.insert(0, str(ETL_DIR))
os.chdir(ETL_DIR)

import duckdb
from config.settings import settings

DB_PATH = settings.duckdb_path
PARQUET_OUTPUT = REPO_DIR / "ml" / "data" / "export_modelling.parquet"

print("=" * 60)
print("  RADAR Pangan — DuckDB Direct Transform")
print("=" * 60)
print(f"  DuckDB : {DB_PATH}")
print(f"  Output : {PARQUET_OUTPUT}")
print("=" * 60)

conn = duckdb.connect(DB_PATH)

# ── Step 1: Staging (VIEW) ────────────────────────────────────────────────────
print("\n[1/3] Creating staging VIEW ...")

STAGING_SQL = """
CREATE OR REPLACE VIEW staging.stg_harga_pangan AS
WITH source AS (
    SELECT * FROM raw.harga_pangan
),
cleaned AS (
    SELECT
        CAST(tanggal AS DATE)                           AS tanggal,
        comcat_id,
        TRIM(komoditas_nama)                            AS komoditas_nama,
        CAST(pasar_tipe AS INTEGER)                     AS pasar_tipe,
        CAST(provinsi_id AS INTEGER)                    AS provinsi_id,
        TRIM(provinsi_nama)                             AS provinsi_nama,
        CAST(kota_id AS INTEGER)                        AS kota_id,
        TRIM(kota_nama)                                 AS kota_nama,
        TRIM(pasar_nama)                                AS pasar_nama,
        CASE WHEN harga <= 0 THEN NULL ELSE CAST(harga AS DOUBLE) END AS harga,
        LOWER(TRIM(satuan))                             AS satuan,
        CASE pasar_tipe
            WHEN 1 THEN 'Pasar Tradisional'
            WHEN 2 THEN 'Pasar Modern'
            WHEN 3 THEN 'Pedagang Besar'
            WHEN 4 THEN 'Produsen'
            ELSE 'Tidak Diketahui'
        END                                             AS pasar_tipe_label,
        EXTRACT(YEAR FROM tanggal)                      AS tahun,
        EXTRACT(MONTH FROM tanggal)                     AS bulan,
        EXTRACT(QUARTER FROM tanggal)                   AS kuartal,
        EXTRACT(DOW FROM tanggal)                       AS hari_dalam_minggu,
        DATE_TRUNC('week', tanggal)                     AS minggu,
        DATE_TRUNC('month', tanggal)                    AS bulan_pertama,
        _extracted_at,
        _source
    FROM source
    WHERE tanggal IS NOT NULL
      AND comcat_id IS NOT NULL
      AND comcat_id != ''
),
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY tanggal, comcat_id, kota_id, pasar_nama
            ORDER BY _extracted_at DESC
        ) AS rn
    FROM cleaned
)
SELECT * EXCLUDE (rn)
FROM deduped
WHERE rn = 1
"""

conn.execute("CREATE SCHEMA IF NOT EXISTS staging")
conn.execute(STAGING_SQL)
count = conn.execute("SELECT COUNT(*) FROM staging.stg_harga_pangan").fetchone()[0]
print(f"     ✓ stg_harga_pangan VIEW siap — {count:,} rows")

# ── Step 2: Mart Modelling (TABLE) ───────────────────────────────────────────
print("\n[2/3] Building mart_modelling_harga_pangan TABLE ...")
print("     (ini butuh beberapa menit untuk 346K rows dengan window functions)")

MART_SQL = """
CREATE OR REPLACE TABLE marts.mart_modelling_harga_pangan AS
WITH base AS (
    SELECT
        tanggal, comcat_id, komoditas_nama,
        provinsi_id, provinsi_nama, kota_id, kota_nama,
        harga, satuan, tahun, bulan, kuartal, hari_dalam_minggu
    FROM staging.stg_harga_pangan
    WHERE harga IS NOT NULL
      AND pasar_tipe = 1
),
with_lags AS (
    SELECT
        *,
        LAG(harga, 1)  OVER w  AS harga_lag_1d,
        LAG(harga, 7)  OVER w  AS harga_lag_7d,
        LAG(harga, 14) OVER w  AS harga_lag_14d,
        LAG(harga, 30) OVER w  AS harga_lag_30d,
        harga - LAG(harga, 1)  OVER w              AS delta_harga_1d,
        harga - LAG(harga, 7)  OVER w              AS delta_harga_7d,
        CASE
            WHEN LAG(harga, 1) OVER w > 0
            THEN ROUND((harga - LAG(harga, 1) OVER w) / LAG(harga, 1) OVER w * 100, 4)
        END                                         AS pct_change_1d,
        CASE
            WHEN LAG(harga, 7) OVER w > 0
            THEN ROUND((harga - LAG(harga, 7) OVER w) / LAG(harga, 7) OVER w * 100, 4)
        END                                         AS pct_change_7d
    FROM base
    WINDOW w AS (
        PARTITION BY comcat_id, kota_id
        ORDER BY tanggal
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
),
with_rolling AS (
    SELECT
        *,
        AVG(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                           AS rolling_avg_7d,
        STDDEV(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                           AS rolling_std_7d,
        AVG(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_avg_30d,
        STDDEV(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_std_30d,
        MIN(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_min_30d,
        MAX(harga) OVER (
            PARTITION BY comcat_id, kota_id ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_max_30d,
        AVG(harga) OVER (
            PARTITION BY comcat_id, tanggal
        )                                           AS avg_harga_nasional
    FROM with_lags
),
with_calendar AS (
    SELECT
        *,
        CASE WHEN hari_dalam_minggu NOT IN (0, 6) THEN 1 ELSE 0 END AS is_weekday,
        CASE WHEN bulan IN (3, 4, 5) THEN 1 ELSE 0 END              AS is_ramadan_season,
        CASE WHEN bulan IN (12, 1)   THEN 1 ELSE 0 END              AS is_year_end_season,
        CASE
            WHEN rolling_std_30d > 0
            THEN ROUND((harga - rolling_avg_30d) / rolling_std_30d, 4)
        END                                                           AS harga_zscore_30d,
        CASE
            WHEN avg_harga_nasional > 0
            THEN ROUND(harga / avg_harga_nasional, 4)
        END                                                           AS harga_ratio_nasional
    FROM with_rolling
)
SELECT
    tanggal, comcat_id, komoditas_nama,
    provinsi_id, provinsi_nama, kota_id, kota_nama, satuan,
    harga                                           AS harga_aktual,
    harga_lag_1d, harga_lag_7d, harga_lag_14d, harga_lag_30d,
    delta_harga_1d, delta_harga_7d,
    ROUND(pct_change_1d, 4)                         AS pct_change_1d,
    ROUND(pct_change_7d, 4)                         AS pct_change_7d,
    ROUND(rolling_avg_7d, 2)                        AS rolling_avg_7d,
    ROUND(rolling_std_7d, 2)                        AS rolling_std_7d,
    ROUND(rolling_avg_30d, 2)                       AS rolling_avg_30d,
    ROUND(rolling_std_30d, 2)                       AS rolling_std_30d,
    rolling_min_30d, rolling_max_30d,
    ROUND(avg_harga_nasional, 2)                    AS avg_harga_nasional,
    harga_zscore_30d, harga_ratio_nasional,
    tahun, bulan, kuartal, hari_dalam_minggu,
    is_weekday, is_ramadan_season, is_year_end_season
FROM with_calendar
ORDER BY comcat_id, kota_id, tanggal
"""

conn.execute("CREATE SCHEMA IF NOT EXISTS marts")
conn.execute(MART_SQL)
mart_count = conn.execute("SELECT COUNT(*) FROM marts.mart_modelling_harga_pangan").fetchone()[0]
print(f"     ✓ mart_modelling_harga_pangan siap — {mart_count:,} rows")

# ── Step 3: Export to Parquet ─────────────────────────────────────────────────
print(f"\n[3/3] Export ke parquet ...")
PARQUET_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

conn.execute(f"""
    COPY (SELECT * FROM marts.mart_modelling_harga_pangan ORDER BY tanggal, comcat_id, kota_id)
    TO '{PARQUET_OUTPUT.as_posix()}'
    (FORMAT PARQUET, COMPRESSION SNAPPY)
""")

conn.close()

size_mb = PARQUET_OUTPUT.stat().st_size / 1024 / 1024
print(f"     ✓ Tersimpan: {PARQUET_OUTPUT}")
print(f"     ✓ Ukuran   : {size_mb:.1f} MB")
print(f"     ✓ Rows     : {mart_count:,}")

print("\n✓ Semua transformasi selesai!")

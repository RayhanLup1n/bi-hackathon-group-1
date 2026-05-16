"""
Seed dummy data for ML teammate:
1. raw.inflasi_bulanan   — Monthly inflation rates per commodity (6 MVP komoditas)
2. raw.musim_panen       — Harvest season calendar per commodity

Data source: Dummy/estimated values (BPS website was down).
TODO: Replace with real BPS data when available.

Usage:
    uv run python etl/scripts/seed_ml_reference_data.py
"""
from __future__ import annotations

import os
import sys

# Load env
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".envs", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import psycopg2
import psycopg2.extras


def _get_dsn() -> str:
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")
    return f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"


# ── DDL ───────────────────────────────────────────────────────────────────────

DDL_INFLASI = """
CREATE TABLE IF NOT EXISTS raw.inflasi_bulanan (
    id           SERIAL PRIMARY KEY,
    tahun        INTEGER NOT NULL,
    bulan        INTEGER NOT NULL CHECK (bulan BETWEEN 1 AND 12),
    komoditas_id VARCHAR NOT NULL,          -- e.g. 'com_13' (Cabai Merah Besar)
    inflasi_mtm  DOUBLE PRECISION NOT NULL, -- Month-to-Month inflation rate (%)
    inflasi_ytd  DOUBLE PRECISION,          -- Year-to-Date inflation rate (%)
    sumber       VARCHAR DEFAULT 'dummy',   -- 'bps' or 'dummy'
    UNIQUE (tahun, bulan, komoditas_id)
);
"""

DDL_MUSIM_PANEN = """
CREATE TABLE IF NOT EXISTS raw.musim_panen (
    id             SERIAL PRIMARY KEY,
    komoditas_id   VARCHAR NOT NULL,
    komoditas_nama VARCHAR NOT NULL,
    bulan_mulai    INTEGER NOT NULL CHECK (bulan_mulai BETWEEN 1 AND 12),
    bulan_selesai  INTEGER NOT NULL CHECK (bulan_selesai BETWEEN 1 AND 12),
    daerah_utama   VARCHAR NOT NULL,    -- 'Jawa Barat', 'Jawa Tengah', etc.
    catatan        VARCHAR DEFAULT '',
    UNIQUE (komoditas_id, bulan_mulai, daerah_utama)
);
"""

# ── Dummy Inflation Data ──────────────────────────────────────────────────────
# Estimated monthly M-to-M inflation for 6 MVP commodities
# Pattern: cabai/bawang highly volatile, seasonal peaks around Ramadan
# Values are realistic estimates based on BPS historical patterns

INFLASI_DATA = []

# Monthly patterns (Jan-Dec) for each commodity — M-to-M inflation %
# Positive = price increase, Negative = price decrease
INFLASI_PATTERNS: dict[str, list[float]] = {
    # Bawang Merah — puncak Mei-Jun (off-season), turun Aug-Sep (panen)
    "com_11": [2.1, 3.5, 8.2, 5.1, 6.3, 4.2, -2.1, -5.8, -3.2, 1.5, 2.8, 4.1],
    # Bawang Putih — relatif stabil (mostly imported), spike saat impor terganggu
    "com_12": [1.2, 2.1, 4.5, 2.8, 1.5, 0.8, -0.5, -1.2, 0.3, 0.9, 1.8, 3.2],
    # Cabai Merah Besar — sangat volatile, puncak Jan-Mar (musim hujan)
    "com_13": [12.5, 8.3, 15.2, -5.8, -8.2, -3.1, 2.5, 5.8, 3.2, -2.1, 4.5, 9.8],
    # Cabai Merah Keriting — mirip pola cabai besar
    "com_14": [10.8, 7.5, 14.1, -6.2, -7.5, -2.8, 3.1, 6.2, 2.8, -1.5, 5.2, 8.5],
    # Cabai Rawit Hijau — paling volatile, swing besar
    "com_15": [15.2, 10.5, 18.8, -8.5, -12.1, -5.2, 4.8, 8.5, 5.1, -3.2, 7.8, 12.1],
    # Cabai Rawit Merah — volatile, tapi sedikit lebih stabil dari hijau
    "com_16": [13.5, 9.2, 16.5, -7.1, -10.5, -4.5, 3.5, 7.2, 4.2, -2.8, 6.5, 10.8],
}

for comcat_id, monthly_pattern in INFLASI_PATTERNS.items():
    for year in [2024, 2025, 2026]:
        ytd_cumulative = 0.0
        for month_idx, mtm in enumerate(monthly_pattern, 1):
            # 2026: only up to May (current month)
            if year == 2026 and month_idx > 5:
                break
            # Add some yearly variation (±20%)
            import random
            random.seed(hash(f"{comcat_id}-{year}-{month_idx}"))
            variation = random.uniform(0.8, 1.2)
            adjusted_mtm = round(mtm * variation, 1)
            ytd_cumulative += adjusted_mtm
            INFLASI_DATA.append((
                year, month_idx, comcat_id,
                adjusted_mtm,
                round(ytd_cumulative, 1),
                "dummy",
            ))

# ── Musim Panen Data ──────────────────────────────────────────────────────────
# Reference: Kementan, BPS, observasi lapangan
# Bawang merah: 60-80 hari setelah tanam. Panen raya: Jul-Sep (kemarau)
# Bawang putih: 90-120 hari. Panen: Jul-Aug. Mostly imported.
# Cabai: 90-120 hari. Panen banyak di kemarau (Jun-Sep), off-season di hujan (Dec-Feb)

MUSIM_PANEN_DATA = [
    # (komoditas_id, komoditas_nama, bulan_mulai, bulan_selesai, daerah_utama, catatan)
    # Bawang Merah
    ("com_11", "Bawang Merah", 7, 9, "Jawa Barat", "Panen raya kemarau — sentra Brebes, Majalengka"),
    ("com_11", "Bawang Merah", 7, 9, "Jawa Tengah", "Panen raya kemarau — sentra Brebes"),
    ("com_11", "Bawang Merah", 8, 10, "Sulawesi Selatan", "Panen raya agak telat — sentra Enrekang"),
    ("com_11", "Bawang Merah", 1, 3, "Jawa Barat", "Panen off-season (hasil tanam Nov-Des)"),
    # Bawang Putih (mostly imported — local harvest minor)
    ("com_12", "Bawang Putih", 7, 8, "Jawa Barat", "Panen lokal terbatas — mayoritas impor China"),
    ("com_12", "Bawang Putih", 7, 8, "Jawa Tengah", "Panen lokal — sentra Tawangmangu, Temanggung"),
    # Cabai Merah Besar
    ("com_13", "Cabai Merah Besar", 6, 9, "Jawa Barat", "Panen raya kemarau — sentra Garut, Tasikmalaya"),
    ("com_13", "Cabai Merah Besar", 6, 9, "Jawa Tengah", "Panen raya kemarau"),
    ("com_13", "Cabai Merah Besar", 12, 2, "Jawa Barat", "Off-season — produksi turun, harga naik"),
    # Cabai Merah Keriting
    ("com_14", "Cabai Merah Keriting", 6, 9, "Jawa Barat", "Panen raya kemarau"),
    ("com_14", "Cabai Merah Keriting", 6, 9, "Sulawesi Selatan", "Panen kemarau — sentra Gowa, Jeneponto"),
    ("com_14", "Cabai Merah Keriting", 12, 2, "Jawa Barat", "Off-season — harga biasanya tinggi"),
    # Cabai Rawit Hijau
    ("com_15", "Cabai Rawit Hijau", 5, 8, "Jawa Barat", "Panen raya — stok melimpah"),
    ("com_15", "Cabai Rawit Hijau", 5, 8, "Jawa Tengah", "Panen raya"),
    ("com_15", "Cabai Rawit Hijau", 11, 1, "Jawa Barat", "Off-season — curah hujan tinggi, gagal panen"),
    # Cabai Rawit Merah
    ("com_16", "Cabai Rawit Merah", 5, 8, "Jawa Barat", "Panen raya kemarau"),
    ("com_16", "Cabai Rawit Merah", 6, 9, "Sulawesi Selatan", "Panen raya — sentra Gowa"),
    ("com_16", "Cabai Rawit Merah", 11, 1, "Jawa Barat", "Off-season — harga puncak"),
]


def main() -> None:
    print("Connecting to Supabase...")
    conn = psycopg2.connect(_get_dsn())
    cur = conn.cursor()

    try:
        # Create tables
        print("Creating tables...")
        cur.execute(DDL_INFLASI)
        cur.execute(DDL_MUSIM_PANEN)
        conn.commit()
        print("  [OK] raw.inflasi_bulanan")
        print("  [OK] raw.musim_panen")

        # Seed inflasi data (UPSERT)
        print(f"\nSeeding inflasi data ({len(INFLASI_DATA)} rows)...")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO raw.inflasi_bulanan (tahun, bulan, komoditas_id, inflasi_mtm, inflasi_ytd, sumber)
            VALUES %s
            ON CONFLICT (tahun, bulan, komoditas_id) DO UPDATE SET
                inflasi_mtm = EXCLUDED.inflasi_mtm,
                inflasi_ytd = EXCLUDED.inflasi_ytd,
                sumber = EXCLUDED.sumber
            """,
            INFLASI_DATA,
        )
        conn.commit()
        print(f"  [OK] {len(INFLASI_DATA)} rows upserted to raw.inflasi_bulanan")

        # Seed musim panen data (UPSERT)
        print(f"\nSeeding musim panen data ({len(MUSIM_PANEN_DATA)} rows)...")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO raw.musim_panen (komoditas_id, komoditas_nama, bulan_mulai, bulan_selesai, daerah_utama, catatan)
            VALUES %s
            ON CONFLICT (komoditas_id, bulan_mulai, daerah_utama) DO UPDATE SET
                komoditas_nama = EXCLUDED.komoditas_nama,
                bulan_selesai = EXCLUDED.bulan_selesai,
                catatan = EXCLUDED.catatan
            """,
            MUSIM_PANEN_DATA,
        )
        conn.commit()
        print(f"  [OK] {len(MUSIM_PANEN_DATA)} rows upserted to raw.musim_panen")

        # Verify
        cur.execute("SELECT COUNT(*) FROM raw.inflasi_bulanan")
        cnt_inflasi = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM raw.musim_panen")
        cnt_panen = cur.fetchone()[0]
        print(f"\n[DONE] Seed complete!")
        print(f"  raw.inflasi_bulanan: {cnt_inflasi} rows")
        print(f"  raw.musim_panen:     {cnt_panen} rows")

        # Show sample
        cur.execute("""
            SELECT komoditas_id, tahun, bulan, inflasi_mtm, inflasi_ytd
            FROM raw.inflasi_bulanan
            WHERE tahun = 2026
            ORDER BY komoditas_id, bulan
            LIMIT 12
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\nSample (2026):")
            print(f"  {'komoditas':<12} {'bulan':>5} {'MtM%':>8} {'YtD%':>8}")
            for r in rows:
                print(f"  {r[0]:<12} {r[2]:>5} {r[3]:>8.1f} {r[4]:>8.1f}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

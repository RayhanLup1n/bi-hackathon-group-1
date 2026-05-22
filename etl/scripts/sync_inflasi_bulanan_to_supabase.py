"""
Sync inflasi_bulanan dummy data to Supabase app schema.

Creates app.inflasi_bulanan table and seeds improved dummy data
for 6 MVP komoditas from Jan 2020 to May 2026 (current month).

Data patterns are estimated from BPS historical trends:
- Cabai: very volatile, peaks in musim hujan (Dec-Mar), drops during panen (Jun-Sep)
- Bawang Merah: moderate volatility, peaks off-season (Apr-Jun), drops panen (Jul-Sep)
- Bawang Putih: relatively stable (mostly imported), spikes when import disrupted

Usage:
    uv run python etl/scripts/sync_inflasi_bulanan_to_supabase.py
"""
from __future__ import annotations

import os
import sys
import random

# Load env vars from .envs/.env
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".envs", ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

import psycopg2
import psycopg2.extras


def _get_dsn() -> str:
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")
    return (
        f"host={host} port={port} dbname={db} "
        f"user={user} password={password} sslmode=require"
    )


# -- DDL --

DDL_INFLASI = """
CREATE TABLE IF NOT EXISTS app.inflasi_bulanan (
    id           SERIAL PRIMARY KEY,
    tahun        INTEGER NOT NULL,
    bulan        INTEGER NOT NULL CHECK (bulan BETWEEN 1 AND 12),
    komoditas_id VARCHAR NOT NULL,
    inflasi_mtm  DOUBLE PRECISION NOT NULL,
    inflasi_ytd  DOUBLE PRECISION,
    sumber       VARCHAR DEFAULT 'dummy',
    UNIQUE (tahun, bulan, komoditas_id)
);
"""

# -- Monthly M-t-M inflation patterns (Jan-Dec) per commodity --
# Based on BPS historical observation:
# - Positive = price increase, Negative = price decrease
# - Musim hujan (Nov-Mar): supply drops, cabai prices spike
# - Kemarau (Jun-Sep): panen raya, prices drop
# - Ramadan/Lebaran effect: price spike H-14 before

INFLASI_PATTERNS: dict[str, list[float]] = {
    # Bawang Merah - puncak Mei-Jun (off-season), turun Aug-Sep (panen raya)
    "com_11": [2.1, 3.5, 8.2, 5.1, 6.3, 4.2, -2.1, -5.8, -3.2, 1.5, 2.8, 4.1],
    # Bawang Putih - relatif stabil (mostly imported), spike saat impor terganggu
    "com_12": [1.2, 2.1, 4.5, 2.8, 1.5, 0.8, -0.5, -1.2, 0.3, 0.9, 1.8, 3.2],
    # Cabai Merah Besar - sangat volatile, puncak Jan-Mar (musim hujan)
    "com_13": [12.5, 8.3, 15.2, -5.8, -8.2, -3.1, 2.5, 5.8, 3.2, -2.1, 4.5, 9.8],
    # Cabai Merah Keriting - mirip pola cabai besar, sedikit lebih rendah
    "com_14": [10.8, 7.5, 14.1, -6.2, -7.5, -2.8, 3.1, 6.2, 2.8, -1.5, 5.2, 8.5],
    # Cabai Rawit Hijau - paling volatile, swing besar
    "com_15": [15.2, 10.5, 18.8, -8.5, -12.1, -5.2, 4.8, 8.5, 5.1, -3.2, 7.8, 12.1],
    # Cabai Rawit Merah - volatile, tapi sedikit lebih stabil dari hijau
    "com_16": [13.5, 9.2, 16.5, -7.1, -10.5, -4.5, 3.5, 7.2, 4.2, -2.8, 6.5, 10.8],
}

# Year-level modifiers to make each year look different
# Based on real events: 2020 COVID, 2021 recovery, 2022 global inflation,
# 2023 El Nino, 2024 Ramadan shift, 2025-2026 La Nina
YEAR_MODIFIERS: dict[int, float] = {
    2020: 0.7,   # COVID suppressed demand, lower volatility
    2021: 0.85,  # recovery year
    2022: 1.15,  # global inflation, higher commodity prices
    2023: 1.25,  # El Nino - drought impacted agriculture
    2024: 1.0,   # baseline
    2025: 1.1,   # La Nina - wetter conditions
    2026: 1.05,  # moderate
}

# Current cutoff: May 2026
CURRENT_YEAR = 2026
CURRENT_MONTH = 5


def generate_inflasi_data() -> list[tuple]:
    """Generate improved dummy inflation data from 2020 to current month."""
    data: list[tuple] = []

    for comcat_id, monthly_pattern in INFLASI_PATTERNS.items():
        for year in range(2020, CURRENT_YEAR + 1):
            ytd_cumulative = 0.0
            year_mod = YEAR_MODIFIERS.get(year, 1.0)

            for month_idx, base_mtm in enumerate(monthly_pattern, 1):
                # Stop at current month for current year
                if year == CURRENT_YEAR and month_idx > CURRENT_MONTH:
                    break

                # Apply year modifier + random variation (deterministic seed)
                random.seed(hash(f"{comcat_id}-{year}-{month_idx}"))
                noise = random.uniform(0.75, 1.25)
                adjusted_mtm = round(base_mtm * year_mod * noise, 1)

                ytd_cumulative += adjusted_mtm

                data.append((
                    year,
                    month_idx,
                    comcat_id,
                    adjusted_mtm,
                    round(ytd_cumulative, 1),
                    "dummy",
                ))

    return data


def main() -> None:
    inflasi_data = generate_inflasi_data()
    print(f"Generated {len(inflasi_data)} inflation rows")
    print(f"  Coverage: Jan 2020 - {CURRENT_MONTH}/{CURRENT_YEAR}")
    print(f"  Komoditas: {len(INFLASI_PATTERNS)} ({', '.join(INFLASI_PATTERNS.keys())})")

    print("\nConnecting to Supabase...")
    conn = psycopg2.connect(_get_dsn())
    cur = conn.cursor()

    try:
        # Create table in app schema
        print("Creating app.inflasi_bulanan table...")
        cur.execute(DDL_INFLASI)
        conn.commit()
        print("  [OK] app.inflasi_bulanan table ready")

        # Upsert data
        print(f"\nSeeding inflasi data ({len(inflasi_data)} rows)...")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO app.inflasi_bulanan
                (tahun, bulan, komoditas_id, inflasi_mtm, inflasi_ytd, sumber)
            VALUES %s
            ON CONFLICT (tahun, bulan, komoditas_id) DO UPDATE SET
                inflasi_mtm = EXCLUDED.inflasi_mtm,
                inflasi_ytd = EXCLUDED.inflasi_ytd,
                sumber = EXCLUDED.sumber
            """,
            inflasi_data,
        )
        conn.commit()
        print(f"  [OK] {len(inflasi_data)} rows upserted to app.inflasi_bulanan")

        # Verify
        cur.execute("SELECT COUNT(*) FROM app.inflasi_bulanan")
        count = cur.fetchone()[0]
        print(f"\n[DONE] Total rows in app.inflasi_bulanan: {count}")

        # Show summary per year
        cur.execute("""
            SELECT tahun, COUNT(*) as rows, COUNT(DISTINCT komoditas_id) as komoditas
            FROM app.inflasi_bulanan
            GROUP BY tahun
            ORDER BY tahun
        """)
        rows = cur.fetchall()
        print(f"\n{'Tahun':>5} {'Rows':>6} {'Komoditas':>10}")
        print("-" * 25)
        for r in rows:
            print(f"{r[0]:>5} {r[1]:>6} {r[2]:>10}")

        # Show sample for 2026
        cur.execute("""
            SELECT komoditas_id, bulan, inflasi_mtm, inflasi_ytd
            FROM app.inflasi_bulanan
            WHERE tahun = 2026
            ORDER BY komoditas_id, bulan
            LIMIT 12
        """)
        sample = cur.fetchall()
        if sample:
            print(f"\nSample (2026):")
            print(f"  {'ID':<8} {'Bulan':>5} {'MtM%':>8} {'YtD%':>8}")
            for s in sample:
                print(f"  {s[0]:<8} {s[1]:>5} {s[2]:>8.1f} {s[3]:>8.1f}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

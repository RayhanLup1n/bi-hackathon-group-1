"""
Sync musim_panen data to Supabase app schema.

Creates app.musim_panen table and seeds 18 rows of harvest season
reference data for ML teammate.

Previously this data lived in raw.musim_panen (dropped during Supabase cleanup).
Now stored in app.* schema to stay consistent with Gold layer strategy.

Usage:
    uv run python etl/scripts/sync_musim_panen_to_supabase.py
"""
from __future__ import annotations

import os
import sys

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

DDL_MUSIM_PANEN = """
CREATE TABLE IF NOT EXISTS app.musim_panen (
    id             SERIAL PRIMARY KEY,
    komoditas_id   VARCHAR NOT NULL,
    komoditas_nama VARCHAR NOT NULL,
    bulan_mulai    INTEGER NOT NULL CHECK (bulan_mulai BETWEEN 1 AND 12),
    bulan_selesai  INTEGER NOT NULL CHECK (bulan_selesai BETWEEN 1 AND 12),
    daerah_utama   VARCHAR NOT NULL,
    catatan        VARCHAR DEFAULT '',
    UNIQUE (komoditas_id, bulan_mulai, daerah_utama)
);
"""

# -- Harvest Season Data (18 rows) --
# Reference: Kementan, BPS, observasi lapangan
# Bawang merah: 60-80 hari setelah tanam. Panen raya: Jul-Sep (kemarau)
# Bawang putih: 90-120 hari. Panen: Jul-Aug. Mostly imported.
# Cabai: 90-120 hari. Panen banyak di kemarau (Jun-Sep), off-season di hujan (Dec-Feb)

MUSIM_PANEN_DATA = [
    # (komoditas_id, komoditas_nama, bulan_mulai, bulan_selesai, daerah_utama, catatan)
    # Bawang Merah
    ("com_11", "Bawang Merah", 7, 9, "Jawa Barat", "Panen raya kemarau - sentra Brebes, Majalengka"),
    ("com_11", "Bawang Merah", 7, 9, "Jawa Tengah", "Panen raya kemarau - sentra Brebes"),
    ("com_11", "Bawang Merah", 8, 10, "Sulawesi Selatan", "Panen raya agak telat - sentra Enrekang"),
    ("com_11", "Bawang Merah", 1, 3, "Jawa Barat", "Panen off-season (hasil tanam Nov-Des)"),
    # Bawang Putih (mostly imported - local harvest minor)
    ("com_12", "Bawang Putih", 7, 8, "Jawa Barat", "Panen lokal terbatas - mayoritas impor China"),
    ("com_12", "Bawang Putih", 7, 8, "Jawa Tengah", "Panen lokal - sentra Tawangmangu, Temanggung"),
    # Cabai Merah Besar
    ("com_13", "Cabai Merah Besar", 6, 9, "Jawa Barat", "Panen raya kemarau - sentra Garut, Tasikmalaya"),
    ("com_13", "Cabai Merah Besar", 6, 9, "Jawa Tengah", "Panen raya kemarau"),
    ("com_13", "Cabai Merah Besar", 12, 2, "Jawa Barat", "Off-season - produksi turun, harga naik"),
    # Cabai Merah Keriting
    ("com_14", "Cabai Merah Keriting", 6, 9, "Jawa Barat", "Panen raya kemarau"),
    ("com_14", "Cabai Merah Keriting", 6, 9, "Sulawesi Selatan", "Panen kemarau - sentra Gowa, Jeneponto"),
    ("com_14", "Cabai Merah Keriting", 12, 2, "Jawa Barat", "Off-season - harga biasanya tinggi"),
    # Cabai Rawit Hijau
    ("com_15", "Cabai Rawit Hijau", 5, 8, "Jawa Barat", "Panen raya - stok melimpah"),
    ("com_15", "Cabai Rawit Hijau", 5, 8, "Jawa Tengah", "Panen raya"),
    ("com_15", "Cabai Rawit Hijau", 11, 1, "Jawa Barat", "Off-season - curah hujan tinggi, gagal panen"),
    # Cabai Rawit Merah
    ("com_16", "Cabai Rawit Merah", 5, 8, "Jawa Barat", "Panen raya kemarau"),
    ("com_16", "Cabai Rawit Merah", 6, 9, "Sulawesi Selatan", "Panen raya - sentra Gowa"),
    ("com_16", "Cabai Rawit Merah", 11, 1, "Jawa Barat", "Off-season - harga puncak"),
]


def main() -> None:
    print("Connecting to Supabase...")
    conn = psycopg2.connect(_get_dsn())
    cur = conn.cursor()

    try:
        # Create table in app schema
        print("Creating app.musim_panen table...")
        cur.execute(DDL_MUSIM_PANEN)
        conn.commit()
        print("  [OK] app.musim_panen table ready")

        # Upsert data
        print(f"\nSeeding musim panen data ({len(MUSIM_PANEN_DATA)} rows)...")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO app.musim_panen
                (komoditas_id, komoditas_nama, bulan_mulai, bulan_selesai, daerah_utama, catatan)
            VALUES %s
            ON CONFLICT (komoditas_id, bulan_mulai, daerah_utama) DO UPDATE SET
                komoditas_nama = EXCLUDED.komoditas_nama,
                bulan_selesai = EXCLUDED.bulan_selesai,
                catatan = EXCLUDED.catatan
            """,
            MUSIM_PANEN_DATA,
        )
        conn.commit()
        print(f"  [OK] {len(MUSIM_PANEN_DATA)} rows upserted to app.musim_panen")

        # Verify
        cur.execute("SELECT COUNT(*) FROM app.musim_panen")
        count = cur.fetchone()[0]
        print(f"\n[DONE] Total rows in app.musim_panen: {count}")

        # Show sample
        cur.execute("""
            SELECT komoditas_id, komoditas_nama, bulan_mulai, bulan_selesai, daerah_utama
            FROM app.musim_panen
            ORDER BY komoditas_id, bulan_mulai
        """)
        rows = cur.fetchall()
        print(f"\n{'ID':<8} {'Komoditas':<22} {'Mulai':>5} {'Selesai':>7} {'Daerah'}")
        print("-" * 70)
        for r in rows:
            print(f"{r[0]:<8} {r[1]:<22} {r[2]:>5} {r[3]:>7} {r[4]}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

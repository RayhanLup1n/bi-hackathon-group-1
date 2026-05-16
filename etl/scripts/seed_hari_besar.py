"""
Seed hari besar (libur nasional + cuti bersama) ke Supabase PostgreSQL.

Menggunakan python-holidays package sebagai primary source.
Backup: apiliburnasional.vercel.app API.

Usage:
    python scripts/seed_hari_besar.py
    python scripts/seed_hari_besar.py --years 2024 2025 2026 2027
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import psycopg2
from loguru import logger

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import holidays
except ImportError:
    logger.error("Package 'holidays' belum terinstall. Jalankan: pip install holidays")
    sys.exit(1)


def _get_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    # Try loading from .env files
    try:
        from dotenv import load_dotenv
        # Load from ETL .env first, then root .envs/.env
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".envs", ".env"))
    except ImportError:
        pass

    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")

    return f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"


def _categorize_holiday(name: str) -> str:
    """Categorize holiday by type for filtering."""
    name_lower = name.lower()

    if any(k in name_lower for k in ["idul fitri", "idul adha", "isra", "maulid", "tahun baru islam"]):
        return "islam"
    elif any(k in name_lower for k in ["natal", "wafat", "kebangkitan", "kenaikan"]):
        return "kristen"
    elif "nyepi" in name_lower:
        return "hindu"
    elif "waisak" in name_lower:
        return "buddha"
    elif "imlek" in name_lower:
        return "tionghoa"
    elif any(k in name_lower for k in ["kemerdekaan", "pancasila", "buruh"]):
        return "nasional"
    elif "tahun baru masehi" in name_lower:
        return "umum"
    elif "cuti" in name_lower or "joint" in name_lower:
        return "cuti_bersama"
    else:
        return "lainnya"


def generate_hari_besar(years: list[int]) -> list[dict]:
    """Generate hari besar data using python-holidays package."""
    records = []

    for year in years:
        # Public holidays (libur nasional)
        id_public = holidays.Indonesia(
            years=[year],
            categories=("public",),
            language="id",
        )
        for d, name in sorted(id_public.items()):
            records.append({
                "tanggal": d,
                "nama": name,
                "kategori": _categorize_holiday(name),
                "tahun": year,
            })

        # Government holidays (cuti bersama) — only available for years with SKB data
        id_govt = holidays.Indonesia(
            years=[year],
            categories=("government",),
            language="id",
        )
        for d, name in sorted(id_govt.items()):
            # Avoid duplicates with public holidays
            if d not in id_public:
                records.append({
                    "tanggal": d,
                    "nama": f"Cuti Bersama: {name}",
                    "kategori": "cuti_bersama",
                    "tahun": year,
                })

    logger.info(f"Generated {len(records)} hari besar untuk tahun {years}")
    return records


def seed_to_postgres(records: list[dict], dsn: str) -> int:
    """Insert hari besar records ke PostgreSQL."""
    if not records:
        return 0

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # Ensure table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.hari_besar (
                    tanggal     DATE     NOT NULL,
                    nama        VARCHAR  NOT NULL,
                    kategori    VARCHAR,
                    tahun       INTEGER,
                    UNIQUE (tanggal, nama)
                );
            """)

            n_inserted = 0
            for rec in records:
                cur.execute("""
                    INSERT INTO raw.hari_besar (tanggal, nama, kategori, tahun)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tanggal, nama) DO UPDATE SET
                        kategori = EXCLUDED.kategori
                """, (rec["tanggal"], rec["nama"], rec["kategori"], rec["tahun"]))
                n_inserted += cur.rowcount

            conn.commit()
            logger.success(f"Seeded {n_inserted} hari besar ke raw.hari_besar")
            return n_inserted
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Seed hari besar ke PostgreSQL")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2025, 2026, 2027],
        help="Tahun yang akan di-seed (default: 2024-2027)",
    )
    args = parser.parse_args()

    dsn = _get_dsn()
    records = generate_hari_besar(args.years)
    seed_to_postgres(records, dsn)

    # Print summary
    print("\n=== Hari Besar Summary ===")
    from collections import Counter
    by_year = Counter(r["tahun"] for r in records)
    by_kategori = Counter(r["kategori"] for r in records)

    print(f"Total: {len(records)} records")
    print("\nPer tahun:")
    for year, count in sorted(by_year.items()):
        print(f"  {year}: {count}")
    print("\nPer kategori:")
    for kat, count in sorted(by_kategori.items()):
        print(f"  {kat}: {count}")


if __name__ == "__main__":
    main()

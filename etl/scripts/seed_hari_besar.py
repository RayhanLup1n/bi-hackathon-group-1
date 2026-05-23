"""
Seed hari besar (libur nasional + cuti bersama) ke BigQuery raw.hari_besar.

Menggunakan python-holidays package sebagai primary source.
Load via BigQuery batch load (FREE).

Usage:
    python etl/scripts/seed_hari_besar.py
    python etl/scripts/seed_hari_besar.py --years 2024 2025 2026 2027
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import date

# Ensure etl/ is in path for relative imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load credentials from .envs/.env
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_project_root, ".envs", ".env"))
except ImportError:
    pass

import pandas as pd
from google.cloud import bigquery
from loguru import logger

try:
    import holidays
except ImportError:
    logger.error("Package 'holidays' belum terinstall. Jalankan: pip install holidays")
    sys.exit(1)


# -- Config --------------------------------------------------------------------

GCP_PROJECT = os.getenv("GCP_PROJECT", "radar-pangan-hackathon")
BQ_LOCATION = os.getenv("BQ_LOCATION", "asia-southeast2")
BQ_TABLE = f"{GCP_PROJECT}.raw.hari_besar"


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

        # Government holidays (cuti bersama) - only available for years with SKB data
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


def seed_to_bigquery(records: list[dict]) -> int:
    """Load hari besar records to BigQuery raw.hari_besar.

    Uses WRITE_TRUNCATE for idempotent full refresh (small table, ~100 rows).
    """
    if not records:
        return 0

    # Create DataFrame
    df = pd.DataFrame(records)

    # Add id column (sequential starting from 1)
    df["id"] = range(1, len(df) + 1)

    # Fix dtypes for BigQuery
    df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.date
    df["id"] = df["id"].astype("Int64")
    df["tahun"] = df["tahun"].astype("Int64")

    # Reorder columns to match BigQuery schema
    df = df[["id", "tanggal", "nama", "kategori", "tahun"]]

    # Load to BigQuery - WRITE_TRUNCATE because this is a small reference table
    client = bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    load_job = client.load_table_from_dataframe(
        df, BQ_TABLE, job_config=job_config,
    )
    load_job.result()  # Wait for completion

    n_loaded = load_job.output_rows
    logger.success(f"Loaded {n_loaded} hari besar to BigQuery {BQ_TABLE}")
    return n_loaded


def main():
    parser = argparse.ArgumentParser(description="Seed hari besar ke BigQuery")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2025, 2026, 2027],
        help="Tahun yang akan di-seed (default: 2024-2027)",
    )
    args = parser.parse_args()

    records = generate_hari_besar(args.years)
    seed_to_bigquery(records)

    # Print summary
    print("\n=== Hari Besar Summary ===")
    by_year = Counter(r["tahun"] for r in records)
    by_kategori = Counter(r["kategori"] for r in records)

    print(f"Total: {len(records)} records")
    print(f"Target: BigQuery {BQ_TABLE}")
    print("\nPer tahun:")
    for year, count in sorted(by_year.items()):
        print(f"  {year}: {count}")
    print("\nPer kategori:")
    for kat, count in sorted(by_kategori.items()):
        print(f"  {kat}: {count}")


if __name__ == "__main__":
    main()

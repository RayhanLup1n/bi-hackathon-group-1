#!/usr/bin/env python3
"""
run_local_pipeline.py — Standalone ETL pipeline tanpa Docker/Airflow.

Menjalankan pipeline lengkap secara lokal:
  1. Init schema DuckDB
  2. Extract master data (provinsi, kota)
  3. Extract data harga historis dari PIHPS API
  4. Jalankan dbt (staging + mart modelling)
  5. Export mart ke parquet untuk ML training

Cara pakai (dari folder etl/):
    python scripts/run_local_pipeline.py
    python scripts/run_local_pipeline.py --start 2020-01-01 --end 2026-04-26
    python scripts/run_local_pipeline.py --skip-extract  # hanya dbt + export
    python scripts/run_local_pipeline.py --skip-dbt      # hanya extract + export
    python scripts/run_local_pipeline.py --export-only   # hanya export parquet
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────────────────────
ETL_DIR = Path(__file__).parent.parent.resolve()  # bi-hackathon-group-1/etl/
REPO_DIR = ETL_DIR.parent                          # bi-hackathon-group-1/
PARQUET_OUTPUT = REPO_DIR / "ml" / "data" / "export_modelling.parquet"

# Add etl/ to Python path so relative imports work
if str(ETL_DIR) not in sys.path:
    sys.path.insert(0, str(ETL_DIR))

# Change CWD to etl/ so that pydantic-settings can find .env
os.chdir(ETL_DIR)

# ── Settings ──────────────────────────────────────────────────────────────────
TARGET_PROVINCE_IDS = [12, 13]  # Jawa Barat, DKI Jakarta
HISTORICAL_START = date(2020, 1, 1)
HISTORICAL_END = date.today()

# ─────────────────────────────────────────────────────────────────────────────


def step_init_schema():
    """Inisialisasi schema DuckDB."""
    print("\n[1/5] Init schema DuckDB ...")
    from loaders.duckdb_loader import DuckDBLoader
    with DuckDBLoader() as loader:
        loader.init_schema()
    print("     ✓ Schema siap")


def step_extract_master():
    """Extract master data provinsi & kota."""
    print("\n[2/5] Extract master data ...")
    from extractors.pihps_extractor import PihpsExtractor
    from loaders.duckdb_loader import DuckDBLoader

    with PihpsExtractor() as extractor, DuckDBLoader() as loader:
        df_provinsi = extractor.get_master_provinsi()
        if not df_provinsi.empty:
            loader.upsert_provinsi(df_provinsi)
            print(f"     ✓ Provinsi: {len(df_provinsi)} records")

        total_kota = 0
        for prov_id in TARGET_PROVINCE_IDS:
            df_kota = extractor.get_master_kota(province_id=str(prov_id))
            if not df_kota.empty:
                df_kota["provinsi_id"] = prov_id
                df_kota = df_kota.rename(columns={"id": "kota_id", "name": "kota_nama"})
                loader.upsert_kota(df_kota)
                total_kota += len(df_kota)
        print(f"     ✓ Kota: {total_kota} records")


def step_extract_harga(start: date, end: date):
    """Extract data harga per wilayah untuk rentang tanggal tertentu."""
    from extractors.pihps_extractor import PihpsExtractor
    from loaders.duckdb_loader import DuckDBLoader

    run_id = str(uuid.uuid4())

    with DuckDBLoader() as loader:
        last_date = loader.get_last_extracted_date("data_ready_modelling")
        if last_date:
            # Incremental: mulai dari hari setelah yang terakhir di-extract
            effective_start = last_date + timedelta(days=1)
            print(f"\n[3/5] Extract harga (incremental) ...")
            print(f"     Checkpoint ditemukan: {last_date}")
            print(f"     Extract dari {effective_start} → {end}")
        else:
            effective_start = start
            print(f"\n[3/5] Extract harga (full historical) ...")
            print(f"     {effective_start} → {end}")

        if effective_start > end:
            print("     ✓ Data sudah up-to-date, tidak ada yang diextract")
            return

        loader.log_run_start(
            run_id=run_id,
            pipeline_name="data_ready_modelling",
            tanggal_mulai=effective_start,
            tanggal_selesai=end,
        )

    records_inserted = 0
    try:
        with PihpsExtractor() as extractor, DuckDBLoader() as loader:
            df = extractor.extract_harga_per_wilayah(
                tanggal_mulai=effective_start,
                tanggal_selesai=end,
                province_ids=TARGET_PROVINCE_IDS,
            )

            if df.empty:
                print("     [WARNING] Tidak ada data berhasil ditarik!")
            else:
                records_inserted = loader.upsert_harga_pangan(df)
                print(f"     ✓ {records_inserted} records diinsert")

            loader.log_run_finish(
                run_id=run_id,
                status="success",
                records_inserted=records_inserted,
            )
    except Exception as exc:
        from loaders.duckdb_loader import DuckDBLoader as _L
        with _L() as loader:
            loader.log_run_finish(
                run_id=run_id,
                status="failed",
                error_message=str(exc),
            )
        print(f"     [ERROR] Extraction gagal: {exc}")
        raise


def step_dbt():
    """Jalankan dbt untuk staging dan mart modelling."""
    print("\n[4/5] Jalankan dbt ...")
    from config.settings import settings

    dbt_flags = [
        "--project-dir", settings.dbt_project_dir,
        "--profiles-dir", settings.dbt_profiles_dir,
    ]

    # Staging
    print("     Running dbt: staging ...")
    r = subprocess.run(
        ["dbt", "run", "--select", "staging"] + dbt_flags,
        capture_output=True, text=True, cwd=ETL_DIR,
    )
    if r.returncode != 0:
        print(f"     [ERROR] dbt staging gagal:\n{r.stdout}\n{r.stderr}")
        raise RuntimeError("dbt staging failed")
    print("     ✓ staging OK")

    # Mart modelling
    print("     Running dbt: marts.modelling ...")
    r = subprocess.run(
        ["dbt", "run", "--select", "marts.modelling"] + dbt_flags,
        capture_output=True, text=True, cwd=ETL_DIR,
    )
    if r.returncode != 0:
        print(f"     [ERROR] dbt mart modelling gagal:\n{r.stdout}\n{r.stderr}")
        raise RuntimeError("dbt mart modelling failed")
    print("     ✓ mart modelling OK")


def step_export_parquet(output_path: Path):
    """Export mart_modelling ke parquet."""
    print(f"\n[5/5] Export ke parquet ...")
    import duckdb
    from config.settings import settings

    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(settings.duckdb_path, read_only=True)
    try:
        # Hitung dulu berapa baris
        count = conn.execute(
            "SELECT COUNT(*) FROM marts.mart_modelling_harga_pangan"
        ).fetchone()[0]
        print(f"     Total baris di mart: {count:,}")

        # Export
        conn.execute(f"""
            COPY (SELECT * FROM marts.mart_modelling_harga_pangan ORDER BY tanggal, comcat_id, kota_id)
            TO '{output_path.as_posix()}'
            (FORMAT PARQUET, COMPRESSION SNAPPY)
        """)
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"     ✓ Tersimpan ke: {output_path}")
        print(f"     ✓ Ukuran: {size_mb:.1f} MB")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Standalone ETL pipeline untuk RADAR Pangan (tanpa Docker/Airflow)"
    )
    parser.add_argument(
        "--start", default=str(HISTORICAL_START),
        help="Tanggal mulai extraction (YYYY-MM-DD), default: 2020-01-01",
    )
    parser.add_argument(
        "--end", default=str(HISTORICAL_END),
        help="Tanggal selesai extraction (YYYY-MM-DD), default: hari ini",
    )
    parser.add_argument(
        "--skip-extract", action="store_true",
        help="Skip extraction, langsung ke dbt + export",
    )
    parser.add_argument(
        "--skip-dbt", action="store_true",
        help="Skip dbt, langsung export setelah extraction",
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Hanya export parquet dari DuckDB yang sudah ada",
    )
    parser.add_argument(
        "--output", default=str(PARQUET_OUTPUT),
        help=f"Path output parquet (default: {PARQUET_OUTPUT})",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    output_path = Path(args.output)

    print("=" * 60)
    print("  RADAR Pangan — Standalone ETL Pipeline")
    print("=" * 60)
    print(f"  Rentang  : {start_date} → {end_date}")
    print(f"  Output   : {output_path}")

    # Load settings setelah path di-set
    from config.settings import settings
    print(f"  DuckDB   : {settings.duckdb_path}")
    print(f"  dbt dir  : {settings.dbt_project_dir}")
    print("=" * 60)

    if args.export_only:
        step_export_parquet(output_path)
    else:
        if not args.skip_extract:
            step_init_schema()
            step_extract_master()
            step_extract_harga(start_date, end_date)
        if not args.skip_dbt:
            step_dbt()
        step_export_parquet(output_path)

    print("\n✓ Pipeline selesai!")


if __name__ == "__main__":
    main()

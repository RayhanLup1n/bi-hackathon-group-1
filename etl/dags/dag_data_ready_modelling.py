"""
DAG 1: data-ready-modelling
===========================
Tujuan  : Tarik data historis dari BI PIHPS, transformasi, dan hasilkan
          dataset siap training model ML/forecasting.

Mode    : Full load (historical) atau incremental jika ada checkpoint.
Schedule: @once (initial) atau manual trigger untuk historical re-load.
          Setelah initial load, bisa dijadwalkan mingguan untuk update.

Flow:
  init_schema
    → extract_master_data (provinsi, kota)
    → extract_harga_historis
    → load_to_postgres_raw
    → dbt_run_staging
    → dbt_run_mart_modelling
    → dbt_test
    → log_pipeline_finish
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# ── Default args ──────────────────────────────────────────────────────────────
DEFAULT_ARGS = {
    "owner": "bi-pihps-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# Rentang historis: sesuaikan jika perlu
HISTORICAL_START = date(2020, 1, 1)
HISTORICAL_END   = date.today()

PIPELINE_NAME = "data_ready_modelling"

# Import dari centralized config
from config.constants import TARGET_PROVINCE_IDS


# ── Task functions ────────────────────────────────────────────────────────────

def task_init_schema(**ctx):
    """Inisialisasi schema PostgreSQL (Supabase) jika belum ada."""
    from loaders.postgres_loader import PostgresLoader
    with PostgresLoader() as loader:
        loader.init_schema()
    print("Schema PostgreSQL siap.")


def task_extract_master_data(**ctx):
    """Tarik data master: provinsi dan kota (Jawa Barat + DKI Jakarta)."""
    from extractors.pihps_extractor import PihpsExtractor
    from loaders.postgres_loader import PostgresLoader

    with PihpsExtractor() as extractor, PostgresLoader() as loader:
        df_provinsi = extractor.get_master_provinsi()

        if not df_provinsi.empty:
            loader.upsert_provinsi(df_provinsi)
            print(f"  Provinsi: {len(df_provinsi)} record diload")

        # Tarik kota per provinsi target
        total_kota = 0
        for prov_id in TARGET_PROVINCE_IDS:
            df_kota = extractor.get_master_kota(province_id=str(prov_id))
            if not df_kota.empty:
                # Tambah provinsi_id ke data kota
                df_kota["provinsi_id"] = prov_id
                # Rename kolom sesuai schema PostgreSQL
                df_kota = df_kota.rename(columns={"id": "kota_id", "name": "kota_nama"})
                loader.upsert_kota(df_kota)
                total_kota += len(df_kota)
                print(f"  Kota (prov {prov_id}): {len(df_kota)} record diload")

        print(f"  Total kota: {total_kota}")


def task_extract_harga_historis(**ctx):
    """
    Tarik data harga historis per kota (Jawa Barat + DKI Jakarta).
    Support incremental: lanjut dari tanggal terakhir yang sudah diextract.
    """
    from extractors.pihps_extractor import PihpsExtractor
    from loaders.postgres_loader import PostgresLoader

    run_id = ctx["run_id"]

    with PostgresLoader() as loader:
        # Cek checkpoint: apakah ada data sebelumnya?
        last_date = loader.get_last_extracted_date(PIPELINE_NAME)
        tanggal_mulai = (
            last_date + timedelta(days=1) if last_date else HISTORICAL_START
        )
        tanggal_selesai = HISTORICAL_END

        if tanggal_mulai > tanggal_selesai:
            print(f"Data sudah up-to-date sampai {last_date}. Tidak ada yang diextract.")
            ctx["ti"].xcom_push(key="records_inserted", value=0)
            return

        print(f"Extract data per-kota: {tanggal_mulai} → {tanggal_selesai}")
        print(f"Provinsi target: {TARGET_PROVINCE_IDS}")

        # Log start
        loader.log_run_start(
            run_id=run_id,
            pipeline_name=PIPELINE_NAME,
            tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai,
        )

    # Extract per-wilayah
    records_inserted = 0
    try:
        with PihpsExtractor() as extractor, PostgresLoader() as loader:
            df = extractor.extract_harga_per_wilayah(
                tanggal_mulai=tanggal_mulai,
                tanggal_selesai=tanggal_selesai,
                province_ids=TARGET_PROVINCE_IDS,
            )

            if df.empty:
                print("[WARNING] Tidak ada data yang berhasil ditarik!")
            else:
                records_inserted = loader.upsert_harga_pangan(df)
                print(f"Total {records_inserted} record diinsert ke raw.harga_pangan")

            loader.log_run_finish(
                run_id=run_id,
                status="success",
                records_inserted=records_inserted,
            )

    except Exception as exc:
        from loaders.postgres_loader import PostgresLoader as _L
        with _L() as loader:
            loader.log_run_finish(
                run_id=run_id,
                status="failed",
                error_message=str(exc),
            )
        raise

    ctx["ti"].xcom_push(key="records_inserted", value=records_inserted)


def task_dbt_run_staging(**ctx):
    """Jalankan dbt untuk layer staging."""
    import subprocess
    from config.settings import settings

    result = subprocess.run(
        [
            "dbt", "run",
            "--select", "staging",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"dbt staging gagal:\n{result.stderr}")


def task_dbt_run_mart_modelling(**ctx):
    """Jalankan dbt untuk mart modelling."""
    import subprocess
    from config.settings import settings

    result = subprocess.run(
        [
            "dbt", "run",
            "--select", "marts.modelling",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"dbt mart modelling gagal:\n{result.stderr}")


def task_dbt_test(**ctx):
    """Jalankan dbt test untuk validasi kualitas data."""
    import subprocess
    from config.settings import settings

    result = subprocess.run(
        [
            "dbt", "test",
            "--select", "staging mart_modelling_harga_pangan",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    # Test failures → warning saja, tidak fail DAG
    if result.returncode != 0:
        print(f"[WARNING] dbt test ada yang gagal:\n{result.stderr}")


def task_log_summary(**ctx):
    """Log ringkasan hasil pipeline."""
    from loaders.postgres_loader import PostgresLoader

    with PostgresLoader() as loader:
        raw_count = loader.table_row_count("raw.harga_pangan")

        staging_count = loader.table_row_count_safe(
            "staging.stg_harga_pangan",
        )
        mart_count = loader.table_row_count_safe(
            "marts.mart_modelling_harga_pangan",
        )

    records_inserted = ctx["ti"].xcom_pull(
        task_ids="extract_harga_historis",
        key="records_inserted",
    ) or 0

    print("=" * 60)
    print("RINGKASAN PIPELINE: data-ready-modelling")
    print("=" * 60)
    print(f"  Records baru diinsert : {records_inserted:,}")
    print(f"  Total raw             : {raw_count:,}")
    print(f"  Total staging         : {staging_count:,}")
    print(f"  Total mart modelling  : {mart_count:,}")
    print("=" * 60)


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="data_ready_modelling",
    description="Pipeline historis: extract → raw → staging → mart modelling",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,          # trigger manual / @once untuk initial load
    catchup=False,
    tags=["pihps", "modelling", "bi"],
    doc_md=__doc__,
) as dag:

    init_schema = PythonOperator(
        task_id="init_schema",
        python_callable=task_init_schema,
    )

    extract_master = PythonOperator(
        task_id="extract_master_data",
        python_callable=task_extract_master_data,
    )

    extract_historis = PythonOperator(
        task_id="extract_harga_historis",
        python_callable=task_extract_harga_historis,
    )

    dbt_staging = PythonOperator(
        task_id="dbt_run_staging",
        python_callable=task_dbt_run_staging,
    )

    dbt_mart = PythonOperator(
        task_id="dbt_run_mart_modelling",
        python_callable=task_dbt_run_mart_modelling,
    )

    dbt_test = PythonOperator(
        task_id="dbt_test",
        python_callable=task_dbt_test,
    )

    log_summary = PythonOperator(
        task_id="log_summary",
        python_callable=task_log_summary,
    )

    # ── Task dependencies ─────────────────────────────────────────────────
    init_schema >> extract_master >> extract_historis >> dbt_staging >> dbt_mart >> dbt_test >> log_summary

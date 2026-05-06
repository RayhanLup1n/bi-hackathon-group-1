"""
DAG 2: data-ready-dashboard
============================
Tujuan  : Tarik data harian dari BI PIHPS, transformasi, dan hasilkan
          dataset siap konsumsi untuk dashboard monitoring harga pangan.

Mode    : Incremental daily — hanya data hari ini (atau kemarin jika PIHPS
          baru update data di sore/malam hari).

Schedule: Setiap hari jam 07:00 WIB (00:00 UTC).

Flow:
  init_schema
    → check_source_availability
    → extract_harga_harian
    → load_to_postgres_raw
    → dbt_run_staging
    → dbt_run_mart_dashboard
    → dbt_test
    → log_pipeline_finish
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

# ── Default args ──────────────────────────────────────────────────────────────
DEFAULT_ARGS = {
    "owner": "bi-pihps-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
    # Jika gagal, tidak lanjut ke task berikutnya
    "depends_on_past": False,
}

PIPELINE_NAME = "data_ready_dashboard"

# Provinsi target — sama dengan modelling
TARGET_PROVINCE_IDS = [12, 13]  # Jawa Barat, DKI Jakarta


# ── Task functions ────────────────────────────────────────────────────────────

def task_init_schema(**ctx):
    """Inisialisasi schema PostgreSQL (Supabase) jika belum ada."""
    from loaders.postgres_loader import PostgresLoader
    with PostgresLoader() as loader:
        loader.init_schema()
    print("Schema PostgreSQL siap.")


def task_check_source(**ctx):
    """
    Cek apakah source PIHPS dapat diakses sebelum mulai extraction.
    Fail early jika website/API tidak accessible.
    """
    import httpx
    from config.settings import settings

    try:
        resp = httpx.get(settings.base_url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        print(f"Source PIHPS accessible: HTTP {resp.status_code}")
    except Exception as e:
        raise RuntimeError(f"Source PIHPS tidak dapat diakses: {e}")


def task_extract_harga_harian(**ctx):
    """
    Extract data harga harian per kota (Jawa Barat + DKI Jakarta).

    PIHPS biasanya update data D+0 atau D+1.
    Kita tarik data untuk tanggal kemarin agar lebih reliable.
    """
    from extractors.pihps_extractor import PihpsExtractor
    from loaders.postgres_loader import PostgresLoader

    run_id = ctx["run_id"]

    # Gunakan execution date Airflow → tarik data untuk hari tersebut
    execution_date: datetime = ctx["data_interval_end"]
    tanggal_target = execution_date.date() - timedelta(days=1)  # D-1 lebih aman

    print(f"Extraction target: {tanggal_target}")
    print(f"Provinsi target: {TARGET_PROVINCE_IDS}")

    with PostgresLoader() as loader:
        loader.log_run_start(
            run_id=run_id,
            pipeline_name=PIPELINE_NAME,
            tanggal_mulai=tanggal_target,
            tanggal_selesai=tanggal_target,
        )

    records_inserted = 0
    try:
        with PihpsExtractor() as extractor, PostgresLoader() as loader:
            df = extractor.extract_harga_per_wilayah(
                tanggal_mulai=tanggal_target,
                tanggal_selesai=tanggal_target,
                province_ids=TARGET_PROVINCE_IDS,
            )

            if df.empty:
                print(f"[WARNING] Tidak ada data untuk tanggal {tanggal_target}")
            else:
                records_inserted = loader.upsert_harga_pangan(df)
                print(f"{records_inserted} record baru diinsert untuk {tanggal_target}")

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
    ctx["ti"].xcom_push(key="tanggal_target", value=str(tanggal_target))


def task_dbt_run_staging(**ctx):
    """Jalankan dbt staging (incremental update)."""
    import subprocess
    from config.settings import settings

    tanggal_target = ctx["ti"].xcom_pull(
        task_ids="extract_harga_harian",
        key="tanggal_target",
    )

    result = subprocess.run(
        [
            "dbt", "run",
            "--select", "staging",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
            "--vars", f'{{"tanggal_filter": "{tanggal_target}"}}',
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"dbt staging gagal:\n{result.stderr}")


def task_dbt_run_mart_dashboard(**ctx):
    """Jalankan dbt untuk mart dashboard."""
    import subprocess
    from config.settings import settings

    tanggal_target = ctx["ti"].xcom_pull(
        task_ids="extract_harga_harian",
        key="tanggal_target",
    )

    result = subprocess.run(
        [
            "dbt", "run",
            "--select", "marts.dashboard",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
            "--vars", f'{{"tanggal_filter": "{tanggal_target}"}}',
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"dbt mart dashboard gagal:\n{result.stderr}")


def task_dbt_test_dashboard(**ctx):
    """Validasi kualitas data mart dashboard."""
    import subprocess
    from config.settings import settings

    result = subprocess.run(
        [
            "dbt", "test",
            "--select", "mart_dashboard_harga_pangan mart_dashboard_ringkasan_nasional",
            "--project-dir", settings.dbt_project_dir,
            "--profiles-dir", settings.dbt_profiles_dir,
            "--target", settings.dbt_target,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[WARNING] dbt test ada yang gagal:\n{result.stderr}")


def task_log_summary(**ctx):
    """Log ringkasan hasil pipeline harian."""
    from loaders.postgres_loader import PostgresLoader

    records_inserted = ctx["ti"].xcom_pull(
        task_ids="extract_harga_harian",
        key="records_inserted",
    ) or 0
    tanggal_target = ctx["ti"].xcom_pull(
        task_ids="extract_harga_harian",
        key="tanggal_target",
    )

    with PostgresLoader() as loader:
        dashboard_count = loader.table_row_count_safe(
            "marts.mart_dashboard_harga_pangan",
        )
        nasional_count = loader.table_row_count_safe(
            "marts.mart_dashboard_ringkasan_nasional",
        )

    print("=" * 60)
    print("RINGKASAN PIPELINE: data-ready-dashboard")
    print("=" * 60)
    print(f"  Tanggal target        : {tanggal_target}")
    print(f"  Records baru diinsert : {records_inserted:,}")
    print(f"  Total dashboard kota  : {dashboard_count:,}")
    print(f"  Total ringkasan nasional: {nasional_count:,}")
    print("=" * 60)


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="data_ready_dashboard",
    description="Pipeline harian: extract D-1 → raw → staging → mart dashboard",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 0 * * *",    # Setiap hari jam 00:00 UTC (07:00 WIB)
    catchup=False,                    # Tidak backfill otomatis
    max_active_runs=1,                # Hanya 1 run aktif sekaligus
    tags=["pihps", "dashboard", "daily", "bi"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    init_schema = PythonOperator(
        task_id="init_schema",
        python_callable=task_init_schema,
    )

    check_source = PythonOperator(
        task_id="check_source_availability",
        python_callable=task_check_source,
    )

    extract_harian = PythonOperator(
        task_id="extract_harga_harian",
        python_callable=task_extract_harga_harian,
    )

    dbt_staging = PythonOperator(
        task_id="dbt_run_staging",
        python_callable=task_dbt_run_staging,
    )

    dbt_dashboard = PythonOperator(
        task_id="dbt_run_mart_dashboard",
        python_callable=task_dbt_run_mart_dashboard,
    )

    dbt_test = PythonOperator(
        task_id="dbt_test_dashboard",
        python_callable=task_dbt_test_dashboard,
    )

    log_summary = PythonOperator(
        task_id="log_summary",
        python_callable=task_log_summary,
    )

    end = EmptyOperator(task_id="end")

    # ── Task dependencies ─────────────────────────────────────────────────
    (
        start
        >> init_schema
        >> check_source
        >> extract_harian
        >> dbt_staging
        >> dbt_dashboard
        >> dbt_test
        >> log_summary
        >> end
    )

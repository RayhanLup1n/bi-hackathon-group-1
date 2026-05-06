"""
PostgreSQL loader: schema initialization dan data loading ke Supabase.

Migrasi dari DuckDB loader — interface yang sama, backend PostgreSQL.

Layer arsitektur:
  raw       → data mentah dari source, tidak diubah
  staging   → cleaning minimal (dikerjakan oleh dbt VIEW)
  marts     → aggregasi & feature engineering (dikerjakan oleh dbt TABLE)
  app       → application-managed tables (users, het, ml_predictions)
"""
from __future__ import annotations

import os
from datetime import date
from contextlib import contextmanager

import pandas as pd
import psycopg2
import psycopg2.extras
from loguru import logger


def _get_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")

    return f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"


# ── DDL Schema ────────────────────────────────────────────────────────────────

DDL_SCHEMAS = [
    "CREATE SCHEMA IF NOT EXISTS raw;",
    "CREATE SCHEMA IF NOT EXISTS staging;",
    "CREATE SCHEMA IF NOT EXISTS marts;",
    "CREATE SCHEMA IF NOT EXISTS app;",
]

DDL_RAW_HARGA_PANGAN = """
CREATE TABLE IF NOT EXISTS raw.harga_pangan (
    tanggal          DATE         NOT NULL,
    comcat_id        VARCHAR,
    komoditas_nama   VARCHAR,
    pasar_tipe       INTEGER,
    provinsi_id      INTEGER,
    provinsi_nama    VARCHAR,
    kota_id          INTEGER,
    kota_nama        VARCHAR,
    pasar_nama       VARCHAR,
    harga            DOUBLE PRECISION,
    satuan           VARCHAR,
    _extracted_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    _source          VARCHAR      DEFAULT 'bi_pihps'
);
"""

DDL_RAW_PROVINSI = """
CREATE TABLE IF NOT EXISTS raw.dim_provinsi (
    provinsi_id      INTEGER PRIMARY KEY,
    provinsi_nama    VARCHAR,
    _extracted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_RAW_KOTA = """
CREATE TABLE IF NOT EXISTS raw.dim_kota (
    kota_id          INTEGER PRIMARY KEY,
    kota_nama        VARCHAR,
    provinsi_id      INTEGER,
    _extracted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_RAW_PIPELINE_LOG = """
CREATE TABLE IF NOT EXISTS raw.pipeline_log (
    run_id           VARCHAR      NOT NULL,
    pipeline_name    VARCHAR      NOT NULL,
    tanggal_mulai    DATE,
    tanggal_selesai  DATE,
    records_inserted INTEGER      DEFAULT 0,
    status           VARCHAR      DEFAULT 'running',
    error_message    TEXT,
    started_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMP
);
"""

DDL_RAW_HARI_BESAR = """
CREATE TABLE IF NOT EXISTS raw.hari_besar (
    tanggal          DATE         NOT NULL,
    nama             VARCHAR      NOT NULL,
    kategori         VARCHAR,
    tahun            INTEGER,
    UNIQUE (tanggal, nama)
);
"""

# ── App tables ────────────────────────────────────────────────────────────────

DDL_APP_USERS = """
CREATE TABLE IF NOT EXISTS app.users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR      NOT NULL UNIQUE,
    password_hash    VARCHAR      NOT NULL,
    role             VARCHAR      NOT NULL DEFAULT 'viewer',
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_APP_HET_REFERENCE = """
CREATE TABLE IF NOT EXISTS app.het_reference (
    id               SERIAL PRIMARY KEY,
    komoditas_nama   VARCHAR      NOT NULL,
    provinsi_nama    VARCHAR,
    het_harga        DOUBLE PRECISION NOT NULL,
    satuan           VARCHAR      DEFAULT 'kg',
    berlaku_mulai    DATE,
    berlaku_sampai   DATE,
    sumber           VARCHAR      DEFAULT 'dummy',
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_APP_ML_PREDICTIONS = """
CREATE TABLE IF NOT EXISTS app.ml_predictions (
    id               SERIAL PRIMARY KEY,
    komoditas_id     VARCHAR      NOT NULL,
    kota_id          INTEGER      NOT NULL,
    prediction_date  DATE         NOT NULL,
    target_date      DATE         NOT NULL,
    predicted_price  DOUBLE PRECISION,
    confidence_lower DOUBLE PRECISION,
    confidence_upper DOUBLE PRECISION,
    model_version    VARCHAR,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_APP_KOMODITAS_CONFIG = """
CREATE TABLE IF NOT EXISTS app.komoditas_config (
    comcat_id        VARCHAR      PRIMARY KEY,
    komoditas_nama   VARCHAR      NOT NULL,
    is_active        BOOLEAN      DEFAULT TRUE,
    display_order    INTEGER      DEFAULT 0,
    satuan           VARCHAR      DEFAULT 'kg',
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
"""

# ── Indexes ───────────────────────────────────────────────────────────────────

DDL_INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_harga_pangan_lookup
    ON raw.harga_pangan (tanggal, comcat_id, kota_id, pasar_nama);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_harga_pangan_tanggal
    ON raw.harga_pangan (tanggal);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pipeline_log_name
    ON raw.pipeline_log (pipeline_name, status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ml_predictions_lookup
    ON app.ml_predictions (komoditas_id, kota_id, target_date);
    """,
]


class PostgresLoader:
    """
    Handle semua operasi PostgreSQL: koneksi, schema init, dan data loading.

    Pemakaian:
        with PostgresLoader() as loader:
            loader.upsert_harga_pangan(df)
    """

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or _get_dsn()
        self._conn: psycopg2.extensions.connection | None = None

    def _connect(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = False
            logger.debug("PostgreSQL terhubung ke Supabase")
        return self._conn

    @contextmanager
    def _cursor(self):
        """Context manager for cursor with auto-commit/rollback."""
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Schema Init
    # ─────────────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        """Buat schema dan tabel jika belum ada."""
        logger.info("Inisialisasi schema PostgreSQL (Supabase)...")

        with self._cursor() as cur:
            # Create schemas
            for ddl in DDL_SCHEMAS:
                cur.execute(ddl)

            # Create raw tables
            cur.execute(DDL_RAW_HARGA_PANGAN)
            cur.execute(DDL_RAW_PROVINSI)
            cur.execute(DDL_RAW_KOTA)
            cur.execute(DDL_RAW_PIPELINE_LOG)
            cur.execute(DDL_RAW_HARI_BESAR)

            # Create app tables
            cur.execute(DDL_APP_USERS)
            cur.execute(DDL_APP_HET_REFERENCE)
            cur.execute(DDL_APP_ML_PREDICTIONS)
            cur.execute(DDL_APP_KOMODITAS_CONFIG)

            # Create indexes
            for ddl in DDL_INDEXES:
                cur.execute(ddl)

        logger.success("Schema PostgreSQL siap.")

    # ─────────────────────────────────────────────────────────────────────────
    # Data Loading
    # ─────────────────────────────────────────────────────────────────────────

    def upsert_harga_pangan(self, df: pd.DataFrame) -> int:
        """
        Insert data harga pangan ke raw layer.
        Duplikat (tanggal + comcat_id + kota_id + pasar_nama) diabaikan.

        Returns:
            Jumlah baris yang berhasil diinsert
        """
        if df.empty:
            logger.warning("DataFrame kosong, tidak ada data yang diinsert.")
            return 0

        # Deduplikasi sebelum insert
        before = len(df)
        df = df.drop_duplicates(
            subset=["tanggal", "comcat_id", "kota_id", "pasar_nama"],
            keep="last",
        )
        if len(df) < before:
            logger.debug(f"Deduplikasi: {before - len(df)} baris dihapus")

        # Tambah audit columns
        df = df.copy()
        df["_source"] = "bi_pihps"

        # Prepare columns for insert
        columns = [
            "tanggal", "comcat_id", "komoditas_nama", "pasar_tipe",
            "provinsi_id", "provinsi_nama", "kota_id", "kota_nama",
            "pasar_nama", "harga", "satuan", "_source",
        ]

        # Filter only columns that exist in DataFrame
        available_cols = [c for c in columns if c in df.columns]
        records = df[available_cols].values.tolist()

        # Build INSERT with conflict check
        placeholders = ", ".join(["%s"] * len(available_cols))
        col_names = ", ".join(available_cols)

        insert_sql = f"""
            INSERT INTO raw.harga_pangan ({col_names})
            SELECT {placeholders}
            WHERE NOT EXISTS (
                SELECT 1 FROM raw.harga_pangan dst
                WHERE dst.tanggal    = %s
                  AND dst.comcat_id  IS NOT DISTINCT FROM %s
                  AND dst.kota_id    IS NOT DISTINCT FROM %s
                  AND dst.pasar_nama IS NOT DISTINCT FROM %s
            )
        """

        n_inserted = 0
        with self._cursor() as cur:
            for row in records:
                # Build params: insert values + where clause values
                row_dict = dict(zip(available_cols, row))
                where_params = [
                    row_dict.get("tanggal"),
                    row_dict.get("comcat_id"),
                    row_dict.get("kota_id"),
                    row_dict.get("pasar_nama"),
                ]
                params = list(row) + where_params
                cur.execute(insert_sql, params)
                n_inserted += cur.rowcount

        logger.success(f"Insert {n_inserted} record ke raw.harga_pangan")
        return n_inserted

    def upsert_provinsi(self, df: pd.DataFrame) -> None:
        """Insert/update master data provinsi."""
        if df.empty:
            return

        sql = """
            INSERT INTO raw.dim_provinsi (provinsi_id, provinsi_nama)
            VALUES (%s, %s)
            ON CONFLICT (provinsi_id) DO UPDATE SET
                provinsi_nama = EXCLUDED.provinsi_nama,
                _extracted_at = CURRENT_TIMESTAMP
        """

        with self._cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(sql, (row["provinsi_id"], row["provinsi_nama"]))

    def upsert_kota(self, df: pd.DataFrame) -> None:
        """Insert/update master data kota."""
        if df.empty:
            return

        sql = """
            INSERT INTO raw.dim_kota (kota_id, kota_nama, provinsi_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (kota_id) DO UPDATE SET
                kota_nama = EXCLUDED.kota_nama,
                provinsi_id = EXCLUDED.provinsi_id,
                _extracted_at = CURRENT_TIMESTAMP
        """

        with self._cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(sql, (row["kota_id"], row["kota_nama"], row.get("provinsi_id")))

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline Logging
    # ─────────────────────────────────────────────────────────────────────────

    def log_run_start(
        self,
        run_id: str,
        pipeline_name: str,
        tanggal_mulai: date,
        tanggal_selesai: date,
    ) -> None:
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO raw.pipeline_log
                    (run_id, pipeline_name, tanggal_mulai, tanggal_selesai, status)
                VALUES (%s, %s, %s, %s, 'running')
            """, [run_id, pipeline_name, tanggal_mulai, tanggal_selesai])

    def log_run_finish(
        self,
        run_id: str,
        status: str,
        records_inserted: int = 0,
        error_message: str | None = None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute("""
                UPDATE raw.pipeline_log
                SET
                    status           = %s,
                    records_inserted = %s,
                    error_message    = %s,
                    finished_at      = CURRENT_TIMESTAMP
                WHERE run_id = %s
            """, [status, records_inserted, error_message, run_id])

    # ─────────────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────────────

    def get_last_extracted_date(self, pipeline_name: str) -> date | None:
        """Ambil tanggal terakhir yang sudah diextract (untuk incremental load)."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT MAX(tanggal_selesai)
                FROM raw.pipeline_log
                WHERE pipeline_name = %s
                  AND status = 'success'
            """, [pipeline_name])
            result = cur.fetchone()

        if result and result[0]:
            return result[0]
        return None

    def table_row_count(self, table: str) -> int:
        """Jumlah baris dalam suatu tabel (format: schema.table)."""
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            result = cur.fetchone()
        return result[0] if result else 0

    def table_row_count_safe(self, *table_candidates: str) -> int:
        """
        Coba hitung row count dari beberapa kemungkinan nama tabel.
        Returns 0 jika semua kandidat tidak ditemukan.
        """
        for table in table_candidates:
            try:
                return self.table_row_count(table)
            except Exception:
                continue
        return 0

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

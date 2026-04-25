"""
DuckDB loader: schema initialization dan data loading.

Layer arsitektur:
  raw       → data mentah dari source, tidak diubah
  staging   → cleaning minimal, normalisasi tipe data
  (mart)    → dikerjakan oleh dbt
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from loguru import logger

from config.settings import settings

# ── DDL Schema ────────────────────────────────────────────────────────────────

DDL_RAW_HARGA_PANGAN = """
CREATE TABLE IF NOT EXISTS raw.harga_pangan (
    tanggal          DATE         NOT NULL,
    comcat_id        VARCHAR,              -- format "cat_1", "cat_2", dll (dari API PIHPS)
    komoditas_nama   VARCHAR,
    pasar_tipe       INTEGER,              -- 1=tradisional, 2=modern, 3=pedagang_besar, 4=produsen
    provinsi_id      INTEGER,
    provinsi_nama    VARCHAR,
    kota_id          INTEGER,
    kota_nama        VARCHAR,
    pasar_nama       VARCHAR,
    harga            DOUBLE,
    satuan           VARCHAR,
    -- audit columns
    _extracted_at    TIMESTAMP    DEFAULT current_timestamp,
    _source          VARCHAR      DEFAULT 'bi_pihps'
);
"""

DDL_RAW_PROVINSI = """
CREATE TABLE IF NOT EXISTS raw.dim_provinsi (
    provinsi_id      INTEGER PRIMARY KEY,
    provinsi_nama    VARCHAR,
    _extracted_at    TIMESTAMP DEFAULT current_timestamp
);
"""

DDL_RAW_KOTA = """
CREATE TABLE IF NOT EXISTS raw.dim_kota (
    kota_id          INTEGER PRIMARY KEY,
    kota_nama        VARCHAR,
    provinsi_id      INTEGER,
    _extracted_at    TIMESTAMP DEFAULT current_timestamp
);
"""

DDL_RAW_PIPELINE_LOG = """
CREATE TABLE IF NOT EXISTS raw.pipeline_log (
    run_id           VARCHAR      NOT NULL,
    pipeline_name    VARCHAR      NOT NULL,
    tanggal_mulai    DATE,
    tanggal_selesai  DATE,
    records_inserted INTEGER      DEFAULT 0,
    status           VARCHAR      DEFAULT 'running',  -- running | success | failed
    error_message    VARCHAR,
    started_at       TIMESTAMP    DEFAULT current_timestamp,
    finished_at      TIMESTAMP
);
"""


class DuckDBLoader:
    """
    Handle semua operasi DuckDB: koneksi, schema init, dan data loading.

    Pemakaian:
        with DuckDBLoader() as loader:
            loader.upsert_harga_pangan(df)
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or settings.duckdb_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(self._db_path)
            logger.debug(f"DuckDB terhubung: {self._db_path}")
        return self._conn

    # ─────────────────────────────────────────────────────────────────────────
    # Schema Init
    # ─────────────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        """Buat schema dan tabel jika belum ada."""
        conn = self._connect()
        logger.info("Inisialisasi schema DuckDB...")

        conn.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        conn.execute("CREATE SCHEMA IF NOT EXISTS staging;")
        conn.execute("CREATE SCHEMA IF NOT EXISTS marts;")

        conn.execute(DDL_RAW_HARGA_PANGAN)
        conn.execute(DDL_RAW_PROVINSI)
        conn.execute(DDL_RAW_KOTA)
        conn.execute(DDL_RAW_PIPELINE_LOG)

        logger.success("Schema DuckDB siap.")

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

        conn = self._connect()

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

        # Register DataFrame sebagai view sementara
        conn.register("_df_harga_pangan", df)

        # Hitung row count sebelum insert (untuk menghitung selisih)
        count_before = conn.execute(
            "SELECT COUNT(*) FROM raw.harga_pangan"
        ).fetchone()[0]

        # Insert dengan ignore duplikat berdasarkan natural key
        sql = """
            INSERT INTO raw.harga_pangan
                SELECT
                    tanggal::DATE,
                    comcat_id,
                    komoditas_nama,
                    pasar_tipe,
                    provinsi_id,
                    provinsi_nama,
                    kota_id,
                    kota_nama,
                    pasar_nama,
                    harga,
                    satuan,
                    current_timestamp AS _extracted_at,
                    _source
                FROM _df_harga_pangan src
                WHERE NOT EXISTS (
                    SELECT 1 FROM raw.harga_pangan dst
                    WHERE dst.tanggal    = src.tanggal::DATE
                      AND dst.comcat_id  IS NOT DISTINCT FROM src.comcat_id
                      AND dst.kota_id    IS NOT DISTINCT FROM src.kota_id
                      AND dst.pasar_nama IS NOT DISTINCT FROM src.pasar_nama
                )
        """
        conn.execute(sql)
        conn.unregister("_df_harga_pangan")

        # Hitung berapa yang masuk
        # DuckDB tidak punya changes() seperti SQLite,
        # jadi hitung selisih row count sebelum dan sesudah.
        after_count = conn.execute(
            "SELECT COUNT(*) FROM raw.harga_pangan"
        ).fetchone()[0]
        n_inserted = after_count - count_before

        logger.success(f"Insert {n_inserted} record ke raw.harga_pangan")
        return n_inserted

    def upsert_provinsi(self, df: pd.DataFrame) -> None:
        """Insert/update master data provinsi."""
        if df.empty:
            return
        conn = self._connect()
        conn.register("_df_provinsi", df)
        conn.execute("""
            INSERT OR REPLACE INTO raw.dim_provinsi (provinsi_id, provinsi_nama)
            SELECT provinsi_id, provinsi_nama FROM _df_provinsi
        """)
        conn.unregister("_df_provinsi")

    def upsert_kota(self, df: pd.DataFrame) -> None:
        """Insert/update master data kota."""
        if df.empty:
            return
        conn = self._connect()
        conn.register("_df_kota", df)
        conn.execute("""
            INSERT OR REPLACE INTO raw.dim_kota (kota_id, kota_nama, provinsi_id)
            SELECT kota_id, kota_nama, provinsi_id FROM _df_kota
        """)
        conn.unregister("_df_kota")

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
        conn = self._connect()
        conn.execute("""
            INSERT INTO raw.pipeline_log
                (run_id, pipeline_name, tanggal_mulai, tanggal_selesai, status)
            VALUES (?, ?, ?, ?, 'running')
        """, [run_id, pipeline_name, tanggal_mulai, tanggal_selesai])

    def log_run_finish(
        self,
        run_id: str,
        status: str,
        records_inserted: int = 0,
        error_message: str | None = None,
    ) -> None:
        conn = self._connect()
        conn.execute("""
            UPDATE raw.pipeline_log
            SET
                status           = ?,
                records_inserted = ?,
                error_message    = ?,
                finished_at      = current_timestamp
            WHERE run_id = ?
        """, [status, records_inserted, error_message, run_id])

    # ─────────────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────────────

    def get_last_extracted_date(self, pipeline_name: str) -> date | None:
        """Ambil tanggal terakhir yang sudah diextract (untuk incremental load)."""
        conn = self._connect()
        result = conn.execute("""
            SELECT MAX(tanggal_selesai)
            FROM raw.pipeline_log
            WHERE pipeline_name = ?
              AND status = 'success'
        """, [pipeline_name]).fetchone()

        if result and result[0]:
            return result[0]
        return None

    def table_row_count(self, table: str) -> int:
        """Jumlah baris dalam suatu tabel (format: schema.table)."""
        conn = self._connect()
        result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return result[0] if result else 0

    def table_row_count_safe(self, *table_candidates: str) -> int:
        """
        Coba hitung row count dari beberapa kemungkinan nama tabel.
        Berguna karena dbt-duckdb bisa pakai schema 'staging' atau 'main_staging'.
        Returns 0 jika semua kandidat tidak ditemukan.
        """
        for table in table_candidates:
            try:
                return self.table_row_count(table)
            except Exception:
                continue
        return 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

"""
features.py — Feature Engineering untuk ML Layer RADAR Pangan
=============================================================

Tugas:
  1. Load data dari DuckDB (mart_modelling_harga_pangan) atau parquet
  2. Join dengan HET reference (het_reference.csv)
  3. Tambah fitur HET: jarak_ke_het, jarak_ke_het_pct, het_pct_utilization
  4. Tambah target variabel: harga_t7, harga_t14 (forward shift per grup)
  5. Ekspor ke parquet untuk training

Join logic HET (prioritas):
  1. Match by komoditas_nama + provinsi_nama (provinsi-spesifik)
  2. Fall back ke komoditas_nama + "Jawa" (jika Jawa)
  3. Fall back ke komoditas_nama + "Nasional"
  4. Jika tidak ada HET → het_harga = null, has_het = False
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd
from loguru import logger

# ── Konstanta ─────────────────────────────────────────────────────────────────

# Provinsi yang masuk kelompok "Jawa" untuk HET matching
JAWA_PROVINSI = {"DKI Jakarta", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta", "Jawa Timur", "Banten"}

# Feature columns untuk model (exclude identifier + target)
FEATURE_COLS = [
    # Lag features
    "harga_lag_1d", "harga_lag_7d", "harga_lag_14d", "harga_lag_30d",
    "delta_harga_1d", "delta_harga_7d",
    "pct_change_1d", "pct_change_7d",
    # Rolling stats
    "rolling_avg_7d", "rolling_std_7d",
    "rolling_avg_30d", "rolling_std_30d",
    "rolling_min_30d", "rolling_max_30d",
    # Cross-wilayah
    "avg_harga_nasional", "harga_zscore_30d", "harga_ratio_nasional",
    # Calendar
    "bulan", "kuartal", "hari_dalam_minggu",
    "is_weekday", "is_ramadan_season", "is_year_end_season",
    # HET features (added here)
    "het_pct_utilization",  # harga / het_harga * 100 (null jika no HET)
    "jarak_ke_het_pct",     # (harga - het) / het * 100 (null jika no HET)
    # Commodity & location encoding (categorical)
    "comcat_id_encoded",
    "kota_id",
    "provinsi_id",
]

ID_COLS = ["tanggal", "comcat_id", "komoditas_nama", "kota_id", "kota_nama",
           "provinsi_id", "provinsi_nama", "satuan"]

TARGET_COLS = ["harga_t7", "harga_t14"]


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_from_duckdb(
    duckdb_path: str | Path,
    schema: str = "marts",
    table: str = "mart_modelling_harga_pangan",
) -> pd.DataFrame:
    """
    Load mart_modelling_harga_pangan langsung dari DuckDB.

    Args:
        duckdb_path: Path ke file .duckdb
        schema: Schema DuckDB (default: "marts")
        table: Nama tabel (default: "mart_modelling_harga_pangan")

    Returns:
        DataFrame dengan semua kolom dari mart
    """
    logger.info(f"Loading data from DuckDB: {duckdb_path}")
    conn = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        df = conn.execute(f'SELECT * FROM "{schema}"."{table}" ORDER BY tanggal').df()
        logger.info(f"Loaded {len(df):,} rows from {schema}.{table}")
        return df
    finally:
        conn.close()


def load_from_parquet(parquet_path: str | Path) -> pd.DataFrame:
    """Load dari parquet export (untuk dev/training di luar Docker)."""
    logger.info(f"Loading data from parquet: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    logger.info(f"Loaded {len(df):,} rows")
    return df


def load_from_postgres(
    conn_string: str,
    schema: str = "marts",
    table: str = "mart_modelling_harga_pangan",
) -> pd.DataFrame:
    """
    Load mart data dari PostgreSQL (Supabase).

    Args:
        conn_string: SQLAlchemy connection URL,
                     e.g. "postgresql://user:pass@host:port/db"
        schema     : Schema name (default: "marts")
        table      : Table name (default: "mart_modelling_harga_pangan")

    Returns:
        DataFrame dengan semua kolom dari mart
    """
    from sqlalchemy import create_engine, text

    logger.info(f"Loading data from PostgreSQL: {schema}.{table}")
    # statement_timeout=0 disables per-query timeout for this bulk load
    engine = create_engine(
        conn_string,
        connect_args={"options": "-c statement_timeout=0"},
    )
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(f'SELECT * FROM "{schema}"."{table}" ORDER BY tanggal'),
                conn,
            )
        logger.info(f"Loaded {len(df):,} rows from {schema}.{table}")
        return df
    finally:
        engine.dispose()


def export_to_parquet(df: pd.DataFrame, output_path: str | Path) -> None:
    """Export DataFrame ke parquet untuk caching."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    logger.info(f"Exported {len(df):,} rows to {output_path}")


# ── HET Reference Loading & Joining ──────────────────────────────────────────

def _normalize_commodity_name(name: str) -> str:
    """Normalize nama komoditas untuk fuzzy matching (lowercase, strip, no extra spaces)."""
    return re.sub(r"\s+", " ", str(name).lower().strip())


def load_het_reference(het_csv_path: str | Path) -> pd.DataFrame:
    """Load dan prep HET reference CSV."""
    df_het = pd.read_csv(het_csv_path)
    df_het["komoditas_normalized"] = df_het["komoditas_nama"].apply(_normalize_commodity_name)
    df_het["het_harga"] = pd.to_numeric(df_het["het_harga"], errors="coerce")
    logger.info(f"Loaded {len(df_het)} HET records for {df_het['komoditas_nama'].nunique()} commodities")
    return df_het


def _resolve_het(
    komoditas_nama: str,
    provinsi_nama: str,
    het_lookup: dict[tuple[str, str], float],
) -> tuple[float | None, bool]:
    """
    Resolve HET untuk satu (komoditas, provinsi) pair.

    Prioritas:
      1. komoditas + provinsi_nama exact
      2. komoditas + "Jawa" (bila provinsi termasuk Jawa)
      3. komoditas + "Nasional"
      4. None

    Returns:
        (het_harga, has_het)
    """
    k = _normalize_commodity_name(komoditas_nama)

    # 1. Exact provinsi
    if (k, provinsi_nama) in het_lookup:
        return het_lookup[(k, provinsi_nama)], True

    # 2. Jawa group
    if provinsi_nama in JAWA_PROVINSI and (k, "Jawa") in het_lookup:
        return het_lookup[(k, "Jawa")], True

    # 3. Nasional
    if (k, "Nasional") in het_lookup:
        return het_lookup[(k, "Nasional")], True

    return None, False


def add_het_features(df: pd.DataFrame, het_csv_path: str | Path) -> pd.DataFrame:
    """
    Join HET reference ke mart DataFrame dan tambah fitur turunan.

    Kolom yang ditambahkan:
      - het_harga          : HET Rupiah per satuan (null jika tidak ada)
      - has_het            : Boolean — apakah komoditas punya HET
      - jenis_regulasi     : Nama regulasi HET (informational)
      - jarak_ke_het       : harga_aktual - het_harga (Rupiah)
      - jarak_ke_het_pct   : (harga_aktual - het) / het * 100 (persen di atas/bawah HET)
      - het_pct_utilization: harga_aktual / het_harga * 100 (% utilisasi HET, 100=AT HET)
    """
    df_het = load_het_reference(het_csv_path)

    # Build lookup: (komoditas_normalized, provinsi_cakupan) → het_harga
    het_lookup: dict[tuple[str, str], float] = {}
    regulasi_lookup: dict[tuple[str, str], str] = {}
    for _, row in df_het.iterrows():
        key = (row["komoditas_normalized"], row["provinsi_cakupan"])
        het_lookup[key] = row["het_harga"]
        regulasi_lookup[key] = row.get("jenis_regulasi", "")

    logger.info("Resolving HET per (komoditas, provinsi)...")
    resolved = df.apply(
        lambda r: _resolve_het(r["komoditas_nama"], r["provinsi_nama"], het_lookup),
        axis=1,
        result_type="expand",
    )
    df = df.copy()
    df["het_harga"] = resolved[0].astype(float)
    df["has_het"] = resolved[1]

    # Fitur turunan HET
    mask = df["has_het"]
    df["jarak_ke_het"] = np.where(
        mask, df["harga_aktual"] - df["het_harga"], np.nan
    )
    df["jarak_ke_het_pct"] = np.where(
        mask, (df["harga_aktual"] - df["het_harga"]) / df["het_harga"] * 100, np.nan
    )
    df["het_pct_utilization"] = np.where(
        mask, df["harga_aktual"] / df["het_harga"] * 100, np.nan
    )

    n_with_het = df[mask].shape[0]
    n_total = len(df)
    logger.info(
        f"HET joined: {n_with_het:,}/{n_total:,} rows have HET "
        f"({n_with_het/n_total*100:.1f}%)"
    )
    return df


# ── Target Engineering ────────────────────────────────────────────────────────

def add_targets(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """
    Tambah target variabel: harga forward-shifted per (comcat_id, kota_id).

    Misal horizon=7: harga_t7 = harga 7 hari ke depan untuk kombinasi yang sama.
    Baris terakhir per grup (yang tidak memiliki future data) akan NaN — exclude saat training.

    Args:
        df: DataFrame dari mart (harus sudah sorted by tanggal)
        horizons: daftar horizon hari (default: [7, 14])

    Returns:
        DataFrame dengan kolom target tambahan
    """
    if horizons is None:
        horizons = [7, 14]

    df = df.sort_values(["comcat_id", "kota_id", "tanggal"]).copy()

    for h in horizons:
        col = f"harga_t{h}"
        df[col] = df.groupby(["comcat_id", "kota_id"])["harga_aktual"].shift(-h)
        n_valid = df[col].notna().sum()
        logger.info(f"Target harga_t{h}: {n_valid:,} valid rows (shifted -{h})")

    return df


# ── Categorical Encoding ──────────────────────────────────────────────────────

def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Integer-encode comcat_id ("cat_1" → 1) untuk LightGBM.
    kota_id dan provinsi_id sudah integer dari DuckDB.
    """
    df = df.copy()
    df["comcat_id_encoded"] = (
        df["comcat_id"]
        .str.extract(r"(\d+)")[0]
        .astype(float)
        .fillna(0)
        .astype(int)
    )
    return df


# ── Train/Val/Test Split ──────────────────────────────────────────────────────

def prepare_splits(
    df: pd.DataFrame,
    train_end: str = "2024-12-31",
    val_end: str = "2025-12-31",
    horizon: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Rolling time split (no data leakage):
      - Train : tanggal ≤ train_end
      - Val   : train_end < tanggal ≤ val_end
      - Test  : tanggal > val_end

    Rows tanpa target (NaN dari forward shift) di-drop.

    Returns:
        (df_train, df_val, df_test)
    """
    target_col = f"harga_t{horizon}"
    df_clean = df.dropna(subset=[target_col] + ["harga_lag_1d"])  # need at least lag-1

    # Normalise cutoff types to match whatever dtype tanggal has (date or Timestamp)
    sample = df_clean["tanggal"].iloc[0]
    if hasattr(sample, "date"):  # pd.Timestamp
        _train_end = pd.to_datetime(train_end)
        _val_end   = pd.to_datetime(val_end)
    else:  # datetime.date
        import datetime as _dt
        _train_end = _dt.date.fromisoformat(train_end)
        _val_end   = _dt.date.fromisoformat(val_end)

    df_train = df_clean[df_clean["tanggal"] <= _train_end]
    df_val   = df_clean[(df_clean["tanggal"] > _train_end) & (df_clean["tanggal"] <= _val_end)]
    df_test  = df_clean[df_clean["tanggal"] > _val_end]

    logger.info(
        f"Split (horizon={horizon}d): "
        f"train={len(df_train):,} | val={len(df_val):,} | test={len(df_test):,}"
    )
    return df_train, df_val, df_test


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """
    Return daftar feature columns yang tersedia di DataFrame ini.
    Subset dari FEATURE_COLS yang benar-benar ada.
    """
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing = set(FEATURE_COLS) - set(available)
    if missing:
        logger.warning(f"Feature columns tidak tersedia: {missing}")
    return available


# ── Main Pipeline Entry Point ─────────────────────────────────────────────────

def build_feature_dataset(
    source: Literal["duckdb", "parquet"],
    source_path: str | Path,
    het_csv_path: str | Path,
    output_parquet: str | Path | None = None,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Args:
        source       : "duckdb" atau "parquet"
        source_path  : Path ke .duckdb atau .parquet
        het_csv_path : Path ke het_reference.csv
        output_parquet: Jika diberikan, export hasilnya ke parquet
        horizons     : Target horizons (default [7, 14])

    Returns:
        DataFrame siap training
    """
    if source == "duckdb":
        df = load_from_duckdb(source_path)
    else:
        df = load_from_parquet(source_path)

    df = add_het_features(df, het_csv_path)
    df = add_targets(df, horizons or [7, 14])
    df = encode_categoricals(df)

    if output_parquet:
        export_to_parquet(df, output_parquet)

    logger.info(f"Feature dataset ready: {len(df):,} rows × {len(df.columns)} cols")
    return df

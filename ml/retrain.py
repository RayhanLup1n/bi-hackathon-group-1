"""
retrain.py — Refresh data & retrain all LightGBM models with latest data
=========================================================================

Usage (from project root, venv activated):
    python -m ml.retrain [--train-end 2025-12-31] [--val-end 2026-04-30]

Steps:
  1. Pull latest data from app.harga_pangan (includes weather features)
  2. Add HET features, forward-shift targets, categorical encoding
  3. Save refreshed pipeline_cache.parquet (replaces old cache for inference)
  4. Train 4 models: Q50/Q90 × T7/T14 with new time splits
  5. Print metric comparison (old vs new)
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# ── Load .env ─────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env", override=False)

_HOST     = os.environ["SUPABASE_HOST"]
_PORT     = os.environ["SUPABASE_PORT"]
_DB       = os.environ["SUPABASE_DB"]
_USER     = os.environ["SUPABASE_USER"]
_PASSWORD = os.environ["SUPABASE_PASSWORD"]

PG_CONN = f"postgresql://{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_DB}"

MODELS_DIR   = _HERE / "models"
DATA_DIR     = _HERE / "data"
HET_CSV      = DATA_DIR / "het_reference.csv"
CACHE_PATH   = DATA_DIR / "pipeline_cache.parquet"
EXPORT_PATH  = DATA_DIR / "export_modelling.parquet"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_old_metrics() -> dict[str, dict]:
    """Read existing model JSON metadata for before/after comparison."""
    old: dict[str, dict] = {}
    for f in MODELS_DIR.glob("lgbm_*.json"):
        with open(f) as fh:
            m = json.load(fh)
        old[f.stem] = m.get("metrics", {})
    return old


def _print_comparison(old: dict, new: dict) -> None:
    """Print a side-by-side MAPE comparison."""
    print("\n" + "=" * 70)
    print(f"{'MODEL':<22} {'OLD val_mape':>14} {'NEW val_mape':>14}  ΔMAPE")
    print("-" * 70)
    for name in sorted(new):
        o_mape = old.get(name, {}).get("val_mape")
        n_mape = new[name].get("val_mape")
        if o_mape is not None and n_mape is not None:
            delta = n_mape - o_mape
            sign = "▲" if delta > 0 else "▼"
            print(f"{name:<22} {o_mape:>14.3f} {n_mape:>14.3f}  {sign}{abs(delta):.3f}")
        else:
            print(f"{name:<22} {'—':>14} {n_mape:>14.3f}")
    print("=" * 70)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(train_end: str = "2025-12-31", val_end: str = "2026-04-30", from_cache: bool = False) -> None:
    from ml.src.features import (
        add_het_features,
        add_targets,
        encode_categoricals,
        export_to_parquet,
        load_from_harga_pangan,
    )
    from ml.src.train import run_training_pipeline

    # ── Step 1: Pull fresh data (or load from saved cache) ───────────────────
    if from_cache and CACHE_PATH.exists():
        import pandas as pd
        logger.info(f"STEP 1 — Loading from saved cache: {CACHE_PATH}")
        df = pd.read_parquet(CACHE_PATH)
        df["tanggal"] = pd.to_datetime(df["tanggal"])
        logger.info(f"Loaded {len(df):,} rows | {df['tanggal'].min().date()} → {df['tanggal'].max().date()}")
    else:
        logger.info("=" * 60)
        logger.info("STEP 1 — Pulling latest data from app.harga_pangan + weather")
        logger.info("=" * 60)
        raw_df = load_from_harga_pangan(PG_CONN)
        logger.info(f"Raw data: {len(raw_df):,} rows | {raw_df['tanggal'].min().date()} → {raw_df['tanggal'].max().date()}")

        # ── Step 2: Feature engineering ───────────────────────────────────────────
        logger.info("\nSTEP 2 — Adding HET features, targets, encodings")
        df = add_het_features(raw_df, HET_CSV)
        df = add_targets(df, horizons=[7, 14])
        df = encode_categoricals(df)
        logger.info(f"Feature dataset: {len(df):,} rows × {df.shape[1]} cols")

        # ── Step 3: Save refreshed cache ──────────────────────────────────────────
        logger.info("\nSTEP 3 — Saving refreshed pipeline cache")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        export_to_parquet(df, CACHE_PATH)
        logger.info(f"Pipeline cache saved: {CACHE_PATH}")

    # ── Step 4: Train models ───────────────────────────────────────────────────
    logger.info(f"\nSTEP 4 — Training models | train_end={train_end} | val_end={val_end}")
    old_metrics = _load_old_metrics()
    new_metrics = run_training_pipeline(
        df=df,
        models_dir=str(MODELS_DIR),
        train_end=train_end,
        val_end=val_end,
    )

    # ── Step 5: Comparison report ─────────────────────────────────────────────
    _print_comparison(old_metrics, new_metrics)
    logger.info("\nRetrain complete. New .pkl files written to ml/models/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrain RADAR Pangan LightGBM models")
    parser.add_argument("--train-end", default="2025-12-31", help="End of training split (YYYY-MM-DD)")
    parser.add_argument("--val-end",   default="2026-04-30", help="End of validation split (YYYY-MM-DD)")
    parser.add_argument("--from-cache", action="store_true", help="Skip DB fetch, load from saved pipeline_cache.parquet")
    args = parser.parse_args()
    main(train_end=args.train_end, val_end=args.val_end, from_cache=args.from_cache)

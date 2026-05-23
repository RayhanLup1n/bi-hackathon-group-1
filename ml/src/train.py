"""
train.py — LightGBM Quantile Model Training (Lapis 1 — Forecast Engine)
========================================================================

Strategi:
  - Dua model: Q50 (median forecast) dan Q90 (upper-bound risk forecast)
  - Rolling time split: train 2020–2024, val 2025, test 2026+
  - Satu model global menangani semua 21 komoditas × 10 kota
    (lebih efisien, bisa tangkap cross-series patterns via comcat_id/kota_id features)
  - Evaluation: MAPE, Pinball Loss, Coverage (untuk Q90: harus cover ≥90% actuals)
  - Output: models/lgbm_q50_t{horizon}.pkl dan models/lgbm_q90_t{horizon}.pkl

Kenapa satu model global:
  - 210 time series (21 komoditas × 10 kota) = terlalu banyak jika per-series
  - LightGBM bisa encode komoditas + kota sebagai integer fitur
  - Transfer learning implisit: pola cabai di satu kota bantu prediksi kota lain
"""
from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

try:
    import lightgbm as lgb
except ImportError:
    raise ImportError("Install lightgbm: pip install lightgbm")

from ml.src.features import (
    FEATURE_COLS,
    build_feature_dataset,
    get_feature_cols,
    prepare_splits,
)

# ── Default Hyperparameters ───────────────────────────────────────────────────

LGBM_BASE_PARAMS: dict[str, Any] = {
    "objective": "quantile",
    "metric": "quantile",
    "n_estimators": 1000,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": -1,
    "min_child_samples": 30,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "n_jobs": -1,
    "random_state": 42,
    "verbose": -1,
}


# ── Evaluation Metrics ────────────────────────────────────────────────────────

def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error, skip zeros."""
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    """Pinball (quantile) loss."""
    errors = y_true - y_pred
    loss = np.where(errors >= 0, quantile * errors, (quantile - 1) * errors)
    return float(np.mean(loss))


def _coverage(y_true: np.ndarray, y_pred_upper: np.ndarray) -> float:
    """% actuals covered by upper-bound prediction (for Q90: want ≥90%)."""
    return float(np.mean(y_true <= y_pred_upper) * 100)


def evaluate(
    model: lgb.LGBMRegressor,
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    quantile: float,
    split_name: str = "test",
) -> dict[str, float]:
    """Run evaluation for a single model on a DataFrame split."""
    X = df[feature_cols].values
    y_true = df[target_col].values
    y_pred = model.predict(X)

    metrics: dict[str, float] = {
        "mape": _mape(y_true, y_pred),
        "pinball_loss": _pinball_loss(y_true, y_pred, quantile),
        "mae": float(np.mean(np.abs(y_true - y_pred))),
    }

    if quantile >= 0.8:
        metrics["coverage_pct"] = _coverage(y_true, y_pred)

    logger.info(
        f"[{split_name}] Q{quantile:.0%} | "
        f"MAPE={metrics['mape']:.2f}% | "
        f"Pinball={metrics['pinball_loss']:.1f} | "
        f"MAE={metrics['mae']:.0f}"
        + (f" | Coverage={metrics.get('coverage_pct', 0):.1f}%" if "coverage_pct" in metrics else "")
    )
    return metrics


# ── Training ──────────────────────────────────────────────────────────────────

def train_quantile_model(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    quantile: float,
    params: dict[str, Any] | None = None,
) -> lgb.LGBMRegressor:
    """
    Train satu LightGBM Quantile model.

    Args:
        df_train    : Training DataFrame
        df_val      : Validation DataFrame (untuk early stopping)
        feature_cols: Feature column names
        target_col  : Target column (e.g. "harga_t7")
        quantile    : Target quantile (0.5 = median, 0.9 = upper 90th pct)
        params      : Override default LightGBM params

    Returns:
        Trained LGBMRegressor
    """
    p = {**LGBM_BASE_PARAMS, "alpha": quantile, **(params or {})}

    X_train = df_train[feature_cols].values
    y_train = df_train[target_col].values
    X_val   = df_val[feature_cols].values
    y_val   = df_val[target_col].values

    model = lgb.LGBMRegressor(**p)

    logger.info(
        f"Training Q{quantile:.0%} model | "
        f"target={target_col} | "
        f"train={len(df_train):,} | val={len(df_val):,} | "
        f"features={len(feature_cols)}"
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=100),
        ],
    )

    logger.info(f"Q{quantile:.0%} model trained | best_iteration={model.best_iteration_}")
    return model


# ── Save / Load ───────────────────────────────────────────────────────────────

def save_model(
    model: lgb.LGBMRegressor,
    feature_cols: list[str],
    metrics: dict[str, float],
    output_path: str | Path,
) -> None:
    """
    Simpan model + metadata ke .pkl.
    Metadata disimpan juga sebagai .json di samping pkl.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "metrics": metrics,
        "trained_at": datetime.utcnow().isoformat(),
        "best_iteration": model.best_iteration_,
    }

    with open(output_path, "wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)

    # JSON metadata (human-readable)
    meta_path = output_path.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(
            {k: v for k, v in bundle.items() if k != "model"},
            f, indent=2,
        )

    logger.info(f"Model saved: {output_path} | metadata: {meta_path}")


def load_model(model_path: str | Path) -> tuple[lgb.LGBMRegressor, list[str]]:
    """
    Load model + feature_cols dari .pkl.

    Returns:
        (model, feature_cols)
    """
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    logger.info(f"Loaded model from {model_path} | trained_at={bundle.get('trained_at')}")
    return bundle["model"], bundle["feature_cols"]


# ── Full Training Pipeline ────────────────────────────────────────────────────

def run_training_pipeline(
    df: pd.DataFrame,
    models_dir: str | Path,
    horizons: list[int] | None = None,
    quantiles: list[float] | None = None,
    train_end: str = "2024-12-31",
    val_end: str = "2025-12-31",
) -> dict[str, dict[str, float]]:
    """
    Train semua model (tiap horizon × tiap quantile) dan simpan ke models_dir.

    Args:
        df          : Full feature DataFrame (output dari build_feature_dataset)
        models_dir  : Directory untuk menyimpan .pkl model
        horizons    : Forecast horizons (default: [7, 14])
        quantiles   : Target quantiles (default: [0.5, 0.9])
        train_end   : Akhir periode training (YYYY-MM-DD)
        val_end     : Akhir periode validasi (YYYY-MM-DD)

    Returns:
        Dict of all metrics: {model_name: {metric: value}}
    """
    if horizons is None:
        horizons = [7, 14]
    if quantiles is None:
        quantiles = [0.5, 0.9]

    models_dir = Path(models_dir)
    all_metrics: dict[str, dict[str, float]] = {}

    for horizon in horizons:
        target_col = f"harga_t{horizon}"
        df_train, df_val, df_test = prepare_splits(
            df, train_end=train_end, val_end=val_end, horizon=horizon
        )
        feature_cols = get_feature_cols(df_train)

        for q in quantiles:
            model_name = f"lgbm_q{int(q*100)}_t{horizon}"
            logger.info(f"\n{'='*60}\nTraining {model_name}\n{'='*60}")

            model = train_quantile_model(
                df_train, df_val,
                feature_cols=feature_cols,
                target_col=target_col,
                quantile=q,
            )

            # Evaluate on all splits
            val_metrics = evaluate(model, df_val, feature_cols, target_col, q, "val")
            combined_metrics = {f"val_{k}": v for k, v in val_metrics.items()}

            if not df_test.empty:
                test_metrics = evaluate(model, df_test, feature_cols, target_col, q, "test")
                combined_metrics.update({f"test_{k}": v for k, v in test_metrics.items()})
            else:
                logger.warning(f"[{model_name}] Test split is empty — skipping test evaluation.")
            all_metrics[model_name] = combined_metrics

            model_path = models_dir / f"{model_name}.pkl"
            save_model(model, feature_cols, combined_metrics, model_path)

    logger.info(f"\nTraining complete. {len(all_metrics)} models saved to {models_dir}")
    return all_metrics


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train RADAR Pangan ML models")
    parser.add_argument("--source", choices=["duckdb", "parquet"], default="parquet")
    parser.add_argument("--source-path", required=True, help="Path ke .duckdb atau .parquet")
    parser.add_argument("--het-csv", default="ml/data/het_reference.csv")
    parser.add_argument("--models-dir", default="ml/models")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--val-end", default="2025-12-31")
    args = parser.parse_args()

    df = build_feature_dataset(
        source=args.source,
        source_path=args.source_path,
        het_csv_path=args.het_csv,
        output_parquet=None,
    )

    metrics = run_training_pipeline(
        df=df,
        models_dir=args.models_dir,
        train_end=args.train_end,
        val_end=args.val_end,
    )

    print("\n=== Final Metrics Summary ===")
    for model_name, m in metrics.items():
        print(f"\n{model_name}:")
        for k, v in m.items():
            print(f"  {k}: {v:.3f}")

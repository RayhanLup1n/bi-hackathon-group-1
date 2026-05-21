# ML Layer — Training Progress Report
**Date:** 2026-04-26  
**Branch:** `feat/ml-training`  
**Author:** ML Sub-team

---

## Overview

This document records the completion of the ML layer for the **RADAR Pangan** food price monitoring system. The pipeline covers data preparation, feature engineering, LightGBM quantile model training, and evaluation.

---

## Data

| Item | Detail |
|---|---|
| Source | PIHPS API (Panel Harga Pangan — Bank Indonesia) |
| Coverage | 2020-01-01 → 2026-04-26 |
| Cities | 10 kota besar (DKI Jakarta, Surabaya, Bandung, Medan, Makassar, Semarang, Palembang, Balikpapan, Banjarmasin, Manado) |
| Commodities | 21 komoditas pangan strategis |
| Raw records extracted | 346,080 rows |
| After mart filter (pasar tradisional only) | **334,670 rows** |
| Parquet size | 8.1 MB (`ml/data/export_modelling.parquet`) |

---

## Feature Engineering (`ml/src/features.py`)

- **Lag features:** `harga_lag_1d`, `_7d`, `_14d`, `_30d`
- **Rolling statistics:** 7-day, 14-day, 30-day rolling mean + std
- **Calendar features:** day of week, month, week of year, is_weekend, is_ramadan
- **HET price ceiling features:** `het_harga`, `has_het`, `jarak_ke_het`, `jarak_ke_het_pct`, `het_pct_utilization`
- **Anomaly detector output:** `zscore`, `ratio_nasional`
- **Total features used:** 28 (out of 41 engineered columns)

**HET coverage:** 255,006 / 334,670 rows (76.2%) have a valid HET reference price.

---

## Train / Val / Test Splits

Time-based rolling split — no data leakage:

| Split | Period | Rows (horizon=7d) |
|---|---|---|
| Train | ≤ 2024-12-31 | 262,829 |
| Val | 2025-01-01 → 2025-12-31 | 54,411 |
| Test | > 2025-12-31 | 15,750 |

---

## Models Trained

4 LightGBM quantile regression models saved to `ml/models/`:

| Model | Quantile | Horizon | Val MAPE | Test MAPE | Best Iteration |
|---|---|---|---|---|---|
| `lgbm_q50_t7` | Q50 (median) | 7 days | **3.52%** | 3.95% | 158 |
| `lgbm_q90_t7` | Q90 (upper bound) | 7 days | **7.41%** | 7.82% | 371 |
| `lgbm_q50_t14` | Q50 (median) | 14 days | **4.75%** | 5.43% | 534 |
| `lgbm_q90_t14` | Q90 (upper bound) | 14 days | **9.78%** | 9.27% | 239 |

**Target: MAPE ≤ 12% — all models pass.** The Q50 7-day model achieves an exceptional 3.52% val MAPE.

### Q90 Coverage (Interval Calibration)

| Model | Val Coverage | Test Coverage |
|---|---|---|
| `lgbm_q90_t7` | 90.9% | 87.2% |
| `lgbm_q90_t14` | 89.1% | 82.5% |

The 7-day interval is well-calibrated (90.9% ≈ 90% target). The 14-day interval has slightly lower coverage on test data, expected given higher forecast uncertainty.

---

## Artifacts

| File | Description | Committed? |
|---|---|---|
| `ml/src/features.py` | Feature engineering pipeline | ✅ Yes |
| `ml/src/train.py` | Training script with CLI | ✅ Yes |
| `ml/src/detect.py` | Anomaly detector | ✅ Yes |
| `ml/src/decide.py` | Decision logic | ✅ Yes |
| `ml/src/pipeline.py` | End-to-end inference pipeline | ✅ Yes |
| `ml/serve/api.py` | FastAPI inference server | ✅ Yes |
| `ml/models/lgbm_*.json` | Model metadata (features, metrics) | ✅ Yes |
| `ml/models/lgbm_*.pkl` | Model binaries | ❌ No (`.gitignore`) |
| `ml/data/export_modelling.parquet` | Training data export | ❌ No (`.gitignore`) |

---

## How to Reproduce

### 1. Export parquet from DuckDB

```bash
# Run from etl/ directory (requires DuckDB with mart table already populated)
python scripts/run_transforms.py
```

### 2. Train models

```bash
# Run from repo root (bi-hackathon-group-1/)
python -m ml.src.train \
  --source parquet \
  --source-path ml/data/export_modelling.parquet \
  --het-csv ml/data/het_reference.csv \
  --models-dir ml/models
```

### 3. Start inference server

```bash
# Run from repo root
uvicorn ml.serve.api:app --host 0.0.0.0 --port 8001
```

---

## Notes

- `tanggal` column in parquet is stored as `datetime.date` — the `prepare_splits()` function normalises string cutoffs to the correct type before comparison.
- Model `.pkl` files are excluded from git (large binaries). To use the server, run training locally or retrieve models from shared storage.
- The Q90 models serve as the **upper price bound alert** threshold — if actual price exceeds the Q90 forecast, it triggers an anomaly flag.

# Session Log — ML Layer Development

**Tanggal:** 26 April 2026  
**Branch:** `feat/ml-layer`  
**Dikerjakan oleh:** Enzi + GitHub Copilot (Claude Sonnet 4.6)

---

## Ringkasan

Session ini fokus pada pembangunan **ML Layer** dari scratch untuk sistem **RADAR Pangan** — sebuah pipeline prediksi dan deteksi anomali harga pangan berbasis tiga lapis:

1. **Lapis 1 — Forecast Engine:** LightGBM Quantile Regression untuk prediksi harga H+7 dan H+14
2. **Lapis 2 — Detection Engine:** Klasifikasi HET (Harga Eceran Tertinggi), deteksi changepoint online, dan scoring disparitas antar-kota
3. **Lapis 3 — Decision Engine:** AI Agent berbasis OpenAI GPT-4o-mini dengan pola ReAct (Reasoning + Acting) yang menghasilkan narasi rekomendasi intervensi dalam Bahasa Indonesia

Seluruh komponen diekspos melalui **FastAPI inference server** yang siap untuk integrasi dashboard atau microservice lain.

---

## Apa yang Dikerjakan

### 1. Arsitektur 3-Layer ML

Merancang dan mengimplementasikan arsitektur modular yang memisahkan tiga tanggung jawab:

| Layer | Peran | Teknologi |
|-------|-------|-----------|
| Lapis 1 | Numeric forecasting | LightGBM Quantile (Q50, Q90) |
| Lapis 2 | Signal detection | Z-score, HET threshold, Ruptures |
| Lapis 3 | Reasoning & decision | OpenAI GPT-4o-mini + function calling |

Pendekatan satu **global model** (bukan 210 model per series) dipilih agar model bisa belajar pola lintas-komoditas dan lintas-kota, lebih mudah dipelihara, dan lebih efisien untuk inferensi batch.

### 2. HET Reference Data (`ml/data/het_reference.csv`)

Membuat dataset referensi Harga Eceran Tertinggi dari regulasi pemerintah:

- **27 rows** — mencakup seluruh 21 komoditas yang dimonitor
- Sumber: Perpres 125/2022, Permendag 7/2020, Permendag 57/2022, SK Kepmendag 2023, Keputusan Bapanas 2023
- Kolom: `komoditas_nama`, `provinsi_cakupan`, `het_harga`, `satuan`, `jenis_regulasi`, `berlaku_sejak`, `sumber`
- Prioritas join: provinsi exact → `"Jawa"` (coverage Jawa) → `"Nasional"` — untuk menangani kasus khusus seperti HET Daging Ayam yang berbeda antara DKI Jakarta dan Jawa Barat

### 3. Feature Engineering (`ml/src/features.py`)

Membangun pipeline feature engineering yang membaca dari DuckDB atau Parquet:

**Features yang digunakan:**
- Lag harga: `harga_lag_1d`, `harga_lag_7d`, `harga_lag_14d`, `harga_lag_30d`
- Delta & pct_change: `harga_delta_1d`, `harga_pct_change_1d`, `harga_pct_change_7d`, `harga_pct_change_14d`, `harga_pct_change_30d`
- Rolling stats: `harga_rolling_avg_7d`, `harga_rolling_std_7d`, `harga_rolling_avg_30d`, `harga_rolling_std_30d`, `harga_rolling_min_7d`, `harga_rolling_max_7d`
- Calendar: `hari_dalam_minggu`, `minggu_dalam_bulan`, `bulan`, `is_weekday`, `is_ramadan_season`, `is_year_end_season`
- Normalisasi: `harga_zscore_30d`, `harga_ratio_nasional`
- HET (join via fuzzy normalization): `het_harga`, `het_pct_utilization`, `jarak_ke_het_pct`
- Identitas: `comcat_id_encoded`, `kota_id`, `provinsi_id`

**Target variabel:** `harga_h7` (H+7) dan `harga_h14` (H+14) via forward-shift per grup `(comcat_id, kota_id)`

**Split strategy:** Rolling time-split — train 2020–2024, val 2025 (early stopping), test 2026+

### 4. Training Pipeline (`ml/src/train.py`)

Membangun pipeline training LightGBM Quantile Regression:

- Melatih 4 kombinasi model: `{q50, q90} × {h7, h14}`
- Evaluasi metrik: MAPE, Pinball Loss, Coverage (target: MAPE ≤ 12%)
- Menyimpan model sebagai `.pkl` + metadata `.json` (fitur, tanggal training, metrik)
- CLI-capable: `python -m ml.src.train --source parquet --source-path ml/data/export_modelling.parquet`

**Hyperparameter utama:** `n_estimators=1000`, `learning_rate=0.05`, `num_leaves=127`, `early_stopping_rounds=50`

### 5. Detection Engine (`ml/src/detect.py`)

Pure functions (stateless) untuk 3 jenis deteksi:

**HET Alert Classification:**
- `GREEN` — harga < 80% dari HET
- `YELLOW` — harga 80–100% dari HET (zona waspada)
- `RED` — harga ≥ 100% HET (melanggar batas regulasi)
- `UNKNOWN` — komoditas tidak ber-regulasi HET

**Online Changepoint Detection:**
- Membandingkan mean 14 hari terakhir vs baseline 60 hari
- Threshold: z-score > 2.0 → changepoint terdeteksi
- Output: `is_changepoint`, `direction` (RISING/FALLING), `magnitude_pct`

**Batch Changepoint (Offline):**
- Menggunakan `ruptures.Pelt` untuk analisis retrospektif seri panjang

**Disparity Score:**
- `(max_ratio_nasional - min_ratio_nasional) / 2` — normalized [0, 1]
- Mengukur ketimpangan harga antar-kota untuk komoditas yang sama

**`DetectionResult`** menggabungkan ketiga sinyal dengan `final_alert_level` dihitung otomatis di `__post_init__`.

### 6. LLM Reasoning Agent (`ml/src/decide.py`)

Mengimplementasikan AI Agent dengan pola **ReAct (Reasoning + Acting)**:

**4 Tool Functions yang Tersedia untuk LLM:**

| Tool | Deskripsi |
|------|-----------|
| `get_historical_pattern` | Tren harga 30–90 hari terakhir vs seasonality |
| `compare_regional_prices` | Perbandingan harga antar-kota untuk komoditas yang sama |
| `get_upcoming_events` | Deteksi event kalender (Ramadan, Hari Raya, akhir tahun) |
| `get_het_breach_history` | Riwayat frekuensi pelanggaran HET 90 hari ke belakang |

**Alur ReAct:**
1. LLM menerima deteksi sinyal (HET level, changepoint, prediksi, disparity) + data historis
2. LLM memilih tool yang relevan + menjalankannya
3. Tool query in-memory DataFrame (efisien, zero network latency)
4. LLM mempertimbangkan hasil → menghasilkan rekomendasi akhir
5. Maksimum 4 iterasi tool-use dalam satu panggilan

**Fallback rule-based** aktif otomatis jika OPENAI_API_KEY tidak tersedia:
- Weighted scoring: HET 40% + Prediksi 30% + Changepoint 20% + Disparity 10%
- Output tetap konsisten dengan LLM output (struct `DecisionResult` yang sama)

**Output `DecisionResult`:**
- `final_alert_level` — GREEN/YELLOW/RED
- `intervention_priority` — skala 1-5
- `rekomendasi` — narasi Bahasa Indonesia
- `reasoning_trace` — langkah-langkah pemikiran LLM
- `tools_called` — list tools yang dipanggil
- `confidence` — [0.0, 1.0]
- `is_llm_generated` — True jika OpenAI digunakan, False jika rule-based

### 7. Pipeline Orchestrator (`ml/src/pipeline.py`)

Kelas `RadarPipeline` menyatukan ketiga lapis:

- `load()` — load data + 4 model pkl + inisialisasi ReAct agent sekali di startup
- `analyze(komoditas, kota, tanggal)` → `FullAnalysisResult` lengkap
- `analyze_all(tanggal)` → sorted list semua kombinasi, sorted by `intervention_priority`
- `get_active_alerts(tanggal, min_alert_level)` → filtered & sorted alerts untuk alerting sistem

`FullAnalysisResult.to_dict()` ready untuk JSON serialization ke API response.

### 8. FastAPI Inference Server (`ml/serve/api.py`)

Server inferensi dengan 7 endpoints:

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `GET` | `/health` | Health check + status pipeline |
| `POST` | `/api/v1/analyze` | Analisis satu komoditas-kota |
| `POST` | `/api/v1/batch` | Analisis multiple komoditas-kota |
| `GET` | `/api/v1/alerts` | Semua active alerts (filter by level) |
| `GET` | `/api/v1/summary/{tanggal}` | Summary situasi nasional satu tanggal |
| `GET` | `/api/v1/komoditas` | Daftar komoditas yang supported |
| `GET` | `/api/v1/kota` | Daftar kota yang supported |

Pipeline di-load saat startup via `lifespan` event → semua model in-memory → latency inferensi < 100ms per request.

**Konfigurasi via environment variable:**
```
ML_MODELS_DIR, ML_HET_CSV, DUCKDB_PATH, ML_PARQUET_PATH, OPENAI_API_KEY
```

### 9. Dokumentasi ML Layer (`ml/README.md`)

Membuat dokumentasi lengkap yang mencakup:
- Diagram arsitektur 3-layer (ASCII)
- Struktur folder lengkap annotated
- Quick start 5 langkah (install → HET data → train → serve → test)
- Contoh request/response untuk setiap API endpoint
- Penjelasan HET reference data dan langkah pembaruan manual
- Penjelasan LLM ReAct agent (cara kerja, tool list, fallback)
- Opsi integrasi: microservice (via HTTP) vs direct import (via Python)

---

## Hasil Akhir

### File yang Dibuat

| File | Ukuran (approx) | Deskripsi |
|------|-----------------|-----------|
| `ml/data/het_reference.csv` | 27 rows | HET reference data dari regulasi |
| `ml/src/__init__.py` | — | Package marker |
| `ml/src/features.py` | ~250 baris | Feature engineering pipeline |
| `ml/src/train.py` | ~230 baris | LightGBM training + evaluation |
| `ml/src/detect.py` | ~300 baris | Detection engine (3 sinyal) |
| `ml/src/decide.py` | ~380 baris | LLM ReAct agent + rule-based fallback |
| `ml/src/pipeline.py` | ~280 baris | Full 3-layer orchestrator |
| `ml/serve/__init__.py` | — | Package marker |
| `ml/serve/api.py` | ~220 baris | FastAPI inference server |
| `ml/requirements.txt` | — | Python dependencies |
| `ml/.env.example` | — | Template environment variables |
| `ml/.gitignore` | — | Exclude models + .env dari git |
| `ml/models/.gitkeep` | — | Placeholder folder model pkl |
| `ml/notebooks/.gitkeep` | — | Placeholder folder notebooks |
| `ml/README.md` | ~280 baris | Dokumentasi lengkap ML layer |

### Struktur `ml/` Final

```
ml/
├── data/
│   └── het_reference.csv         # HET regulasi pemerintah
├── models/                        # [.gitkeep] — output pkl dari training
├── notebooks/                     # [.gitkeep] — EDA & experiment
├── serve/
│   ├── __init__.py
│   └── api.py                     # FastAPI server
├── src/
│   ├── __init__.py
│   ├── features.py                # Feature engineering
│   ├── train.py                   # Model training
│   ├── detect.py                  # Detection engine
│   ├── decide.py                  # LLM reasoning agent
│   └── pipeline.py                # Orchestrator 3-layer
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

### Target KPI

| KPI | Target | Status |
|-----|--------|--------|
| Forecast MAPE | ≤ 12% | Belum ditraining (butuh data export) |
| Forecast Coverage Q90 | ≥ 85% | Belum ditraining |
| Inference latency per request | < 100ms | Arsitektur in-memory siap |
| HET alert classification | Deterministic (GREEN/YELLOW/RED) | ✅ Implemented |
| LLM fallback jika no API key | Otomatis ke rule-based | ✅ Implemented |

---

## Belum Dikerjakan / Next Steps

- [ ] **Export data DuckDB→Parquet** — perlu `docker cp` dari container ETL. Command:  
  ```bash
  docker exec airflow-webserver python -c "import duckdb; duckdb.connect('/opt/airflow/data/pangan.duckdb').execute(\"COPY (SELECT * FROM marts.mart_modelling_harga_pangan) TO '/tmp/export.parquet' (FORMAT PARQUET)\"); print('Done')"
  docker cp airflow-webserver:/tmp/export.parquet ml/data/export_modelling.parquet
  ```

- [ ] **Training model** — jalankan setelah data Parquet tersedia:  
  ```bash
  cd bi-hackathon-group-1
  pip install -r ml/requirements.txt
  python -m ml.src.train \
    --source parquet \
    --source-path ml/data/export_modelling.parquet \
    --het-csv ml/data/het_reference.csv \
    --models-dir ml/models
  ```

- [ ] **Evaluasi model** — cek MAPE & coverage di test set (2026+), pastikan MAPE ≤ 12%

- [ ] **Jalankan inference server** — setelah model tersimpan di `ml/models/`:  
  ```bash
  cp ml/.env.example ml/.env
  # isi OPENAI_API_KEY di ml/.env
  uvicorn ml.serve.api:app --reload --port 8001
  ```

- [ ] **Notebook EDA** — buat `ml/notebooks/01_eda_and_feature_check.ipynb` untuk eksplorasi distribusi fitur dan validasi HET join

- [ ] **Git commit & push** semua file `ml/` ke branch `feat/ml-layer`

- [ ] **Integrasi dashboard** — connect API endpoint `/api/v1/alerts` dan `/api/v1/summary/{tanggal}` ke dashboard BI / Streamlit yang dibuat tim lain

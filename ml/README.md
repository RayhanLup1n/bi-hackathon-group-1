# ML Layer — RADAR Pangan

Pipeline ML 3 lapis untuk deteksi inflasi, prediksi risiko harga, dan rekomendasi intervensi.

**Stack:** LightGBM Quantile · Bayesian Change Point Detection · OpenAI ReAct Agent · FastAPI

---

## Arsitektur 3 Lapis

```
mart_modelling_harga_pangan  +  het_reference.csv
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  LAPIS 1 — Forecast Engine                           │
│  LightGBM Quantile (Q50 + Q90)                       │
│  → prediksi harga 7 & 14 hari ke depan per wilayah   │
│  → output: harga_pred_p50, harga_pred_p90            │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAPIS 2 — Detection Engine                          │
│  A) Online Change Point Detection (mean-shift test)  │
│  B) HET Threshold Check → green/yellow/red           │
│  C) Disparity Scoring → ketimpangan harga antarkota  │
│  → output: alert_level, is_changepoint, disparity    │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  LAPIS 3 — Decision Engine (LLM Reasoning Agent)     │
│  OpenAI GPT-4o-mini + Function Calling (ReAct)       │
│  Tools: get_historical_pattern, compare_regional,    │
│         get_upcoming_events, get_het_breach_history  │
│  → output: final_alert, priority, rekomendasi (BI)   │
└──────────────────────────────────────────────────────┘
                     │
                     ▼
          FastAPI Inference Server (:8001)
```

---

## Struktur Folder

```
ml/
├── data/
│   ├── het_reference.csv          ← HET per komoditas per wilayah (Bapanas/Permendag)
│   └── *.parquet                  ← Export dari DuckDB (gitignored)
├── models/
│   ├── lgbm_q50_t7.pkl            ← Q50 model, horizon 7 hari
│   ├── lgbm_q90_t7.pkl            ← Q90 model, horizon 7 hari
│   ├── lgbm_q50_t14.pkl           ← Q50 model, horizon 14 hari
│   └── lgbm_q90_t14.pkl           ← Q90 model, horizon 14 hari
├── notebooks/
│   └── 01_eda_and_feature_check.ipynb
├── src/
│   ├── features.py                ← Feature engineering + HET join
│   ├── train.py                   ← Training LightGBM Quantile
│   ├── detect.py                  ← Detection Engine (Lapis 2)
│   ├── decide.py                  ← LLM Reasoning Agent (Lapis 3)
│   └── pipeline.py                ← Orchestrator semua 3 lapis
├── serve/
│   └── api.py                     ← FastAPI inference server
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd bi-hackathon-group-1
pip install -r ml/requirements.txt
```

### 2. Setup Environment

```bash
cp ml/.env.example ml/.env
# Edit ml/.env → isi OPENAI_API_KEY dan DUCKDB_PATH
```

### 3. Export Data dari DuckDB

Data harus tersedia sebelum training. Jika Docker ETL pipeline sudah jalan:

```bash
# Masuk ke container
docker exec -it pihps-airflow-scheduler bash

# Export mart_modelling ke parquet
python -c "
import duckdb, pyarrow.parquet as pq
conn = duckdb.connect('/opt/airflow/data/pihps.duckdb', read_only=True)
df = conn.execute('SELECT * FROM marts.mart_modelling_harga_pangan').df()
df.to_parquet('/opt/airflow/data/export_modelling.parquet', index=False)
print(f'Exported {len(df):,} rows')
"

# Copy ke local
docker cp pihps-airflow-scheduler:/opt/airflow/data/export_modelling.parquet ml/data/
```

### 4. Training Models

```bash
# Training semua model (horizon 7d + 14d, quantile Q50 + Q90)
python -m ml.src.train \
  --source parquet \
  --source-path ml/data/export_modelling.parquet \
  --het-csv ml/data/het_reference.csv \
  --models-dir ml/models \
  --train-end 2024-12-31 \
  --val-end 2025-12-31
```

Training menggunakan rolling time-split (no data leakage):
- **Train**: 2020–2024
- **Val**: 2025 (early stopping)
- **Test**: 2026+ (final eval)

Target metrics: **MAPE ≤ 12%** (sesuai KPI proposal)

### 5. Jalankan Inference Server

```bash
uvicorn ml.serve.api:app --host 0.0.0.0 --port 8001 --reload
```

API tersedia di: http://localhost:8001/docs

---

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/health` | Status pipeline + jumlah model |
| POST | `/api/v1/analyze` | Analisis tunggal (komoditas, kota, tanggal) |
| POST | `/api/v1/batch` | Batch analisis multiple request |
| GET | `/api/v1/alerts` | Semua alert aktif (yellow + red) |
| GET | `/api/v1/summary/{tanggal}` | Ringkasan harian untuk dashboard |
| GET | `/api/v1/komoditas` | Daftar komoditas tersedia |
| GET | `/api/v1/kota` | Daftar kota tersedia |

### Contoh Request

```bash
# Analisis cabai di Bandung hari ini
curl -X POST http://localhost:8001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"komoditas_nama": "Cabai Merah Keriting", "kota_nama": "Bandung", "tanggal": "2026-04-26"}'

# Semua alert aktif hari ini
curl "http://localhost:8001/api/v1/alerts?tanggal=2026-04-26&min_alert_level=yellow"
```

### Contoh Response

```json
{
  "komoditas_nama": "Cabai Merah Keriting",
  "kota_nama": "Bandung",
  "tanggal": "2026-04-26",
  "predictions": {
    "p50_7d": 54200,
    "p90_7d": 61800,
    "p50_14d": 55100,
    "p90_14d": 64300
  },
  "detection": {
    "alert_level": "yellow",
    "pred_alert_level": "red",
    "is_changepoint": true,
    "disparity_score": 0.23,
    "jarak_ke_het_pct": -3.6,
    "het_harga": 55000
  },
  "decision": {
    "final_alert_level": "red",
    "intervention_priority": 1,
    "rekomendasi": "Harga cabai merah keriting Bandung sudah 96.4% dari HET dan prediksi P90 melampaui HET dalam 7 hari. Terdeteksi perubahan regime harga mendadak bertepatan dengan musim Ramadan. Rekomendasikan koordinasi stok dari Jawa Tengah (surplus, ratio 0.87) ke Bandung segera, dikombinasikan dengan operasi pasar untuk stabilisasi harga.",
    "confidence": "high",
    "is_llm_generated": true,
    "reasoning_trace": [
      "[Tool] get_historical_pattern({\"komoditas_nama\": \"Cabai Merah Keriting\", \"bulan\": 4})",
      "[Result] {\"rata_rata_historis_bulan_sama\": 48000, \"pct_change_vs_historis\": 12.9}",
      "[Tool] compare_regional_prices(...)",
      "[Final] ..."
    ]
  }
}
```

---

## HET Reference

File `data/het_reference.csv` berisi HET per komoditas per provinsi berdasarkan regulasi terbaru:
- **Perpres 125/2022** (diperbarui Bapanas 2023) → Beras
- **Permendag 26/2022** → Gula Pasir, Minyak Goreng
- **Kepmendag 2023** → Daging Ayam Ras
- **Acuan Atas Bapanas 2023** → Cabai, Bawang, Daging Sapi, Telur

Kolom: `komoditas_nama, provinsi_cakupan, het_harga, satuan, jenis_regulasi, berlaku_sejak, sumber`

Matching priority: provinsi-spesifik → "Jawa" (untuk provinsi Jawa) → "Nasional"

---

## Lapis 3: LLM Reasoning Agent

Agent menggunakan **OpenAI GPT-4o-mini** dengan pattern **ReAct (Reason + Act)**:

1. Menerima structured signals dari Lapis 1 & 2
2. Memilih tool untuk lookup context tambahan
3. Reasoning berdasarkan semua informasi
4. Output: alert level final + priority + rekomendasi dalam Bahasa Indonesia

**Fallback**: Jika `OPENAI_API_KEY` tidak ada atau API error → rule-based scoring otomatis aktif (tidak ada downtime).

**Tools tersedia:**
| Tool | Fungsi |
|------|--------|
| `get_historical_pattern` | Pola harga per bulan, perbandingan vs historis |
| `compare_regional_prices` | Harga per kota → identifikasi surplus/defisit |
| `get_upcoming_events` | Event musiman 30 hari ke depan |
| `get_het_breach_history` | Frekuensi pelanggaran HET N hari terakhir |

---

## Integrasi dengan Backend Utama

ML layer bisa diintegrasikan dengan backend FastAPI utama (RADAR Pangan) dengan dua cara:

**Option A — HTTP call (microservice):**
```python
import httpx

async def get_ml_analysis(komoditas, kota, tanggal):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://ml-service:8001/api/v1/analyze",
            json={"komoditas_nama": komoditas, "kota_nama": kota, "tanggal": str(tanggal)}
        )
        return r.json()
```

**Option B — Direct import (monolith):**
```python
from ml.src.pipeline import RadarPipeline

pipeline = RadarPipeline.from_config(...)
result   = pipeline.analyze("Cabai Merah Keriting", "Bandung", date.today())
```

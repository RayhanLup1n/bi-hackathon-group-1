# Session Log — 10 Mei 2026

## Ringkasan
Sesi ini berfokus pada dua pekerjaan utama:
1. Integrasi Supabase sebagai satu-satunya sumber data untuk ML pipeline
2. Penguatan sistem deteksi (Layer 2) dengan algoritma CUSUM dan penggantian LLM provider ke OpenRouter

---

## 1. Integrasi Supabase PostgreSQL

### Latar Belakang
Sebelumnya, ML pipeline mendukung tiga sumber data dengan prioritas:
DuckDB (lokal) → Supabase/PostgreSQL → Parquet file.
User memutuskan untuk menggunakan **Supabase sebagai satu-satunya sumber data** (DuckDB dan Parquet dihapus).

### Perubahan

#### `ml/src/features.py`
- Ditambahkan fungsi `load_from_postgres(conn_string, schema, table)` menggunakan SQLAlchemy + psycopg2
- Fungsi membuka koneksi ke Supabase, menjalankan `SELECT * FROM "marts"."mart_modelling_harga_pangan" ORDER BY tanggal`, dan menutup koneksi dengan `engine.dispose()`

#### `ml/src/pipeline.py`
- `load()` dan `from_config()` hanya menerima `pg_conn_string` (DuckDB dan Parquet parameter dihapus)
- Import `load_from_duckdb` dan `load_from_parquet` dihapus

#### `ml/serve/api.py`
- Env var `DUCKDB_PATH` dan `ML_PARQUET_PATH` dihapus
- Ditambahkan pembacaan `SUPABASE_HOST`, `SUPABASE_PORT`, `SUPABASE_DB`, `SUPABASE_USER`, `SUPABASE_PASSWORD`
- `PG_CONN_STRING` dibangun otomatis dari env vars tersebut
- `pipeline.load()` hanya dikirim `pg_conn_string`

#### `ml/requirements.txt`
- Ditambahkan: `psycopg2-binary>=2.9.9` dan `SQLAlchemy>=2.0.0`
- Versi terinstall: `psycopg2-binary-2.9.12`, `SQLAlchemy-2.0.49`

#### `ml/.env.example`
- Dihapus: `DUCKDB_PATH`, `ML_PARQUET_PATH`
- Ditambahkan: `SUPABASE_HOST`, `SUPABASE_PORT`, `SUPABASE_DB`, `SUPABASE_USER`, `SUPABASE_PASSWORD`

#### `ml/.env` (lokal, tidak di-commit)
- Credential Supabase disalin dari `etl/.env`
- Koneksi diverifikasi: **174,290 baris** ditemukan di `marts.mart_modelling_harga_pangan`

---

## 2. Penguatan Detection Engine (Layer 2): Algoritma CUSUM

### Latar Belakang
Detection Engine sebelumnya hanya memiliki satu algoritma change point detection: **Z-score online** yang mendeteksi spike harga tunggal. Kelemahan: membutuhkan perubahan yang sudah besar untuk dideteksi — tidak bisa early warning.

### Solusi: CUSUM (Cumulative Sum Control Chart)

CUSUM adalah metode kontrol statistik klasik yang mengakumulasi deviasi kecil namun konsisten dari baseline. Berbeda dari Z-score:

| | Z-score (existing) | CUSUM (baru) |
|---|---|---|
| Mendeteksi | Spike tunggal besar | Drift kumulatif sustained |
| Waktu deteksi | Setelah lonjakan terjadi | 2–4 hari lebih awal |
| Output | `is_changepoint` (bool) | `is_alarm` (bool) |
| Alert level | `red` | `yellow` (early warning) |

**Algoritma:**
$$\text{CUSUM}^+[t] = \max(0,\ \text{CUSUM}^+[t-1] + z_t - k)$$
$$\text{CUSUM}^-[t] = \max(0,\ \text{CUSUM}^-[t-1] - z_t - k)$$

Di mana:
- $z_t = (x_t - \mu_{\text{baseline}}) / \sigma_{\text{baseline}}$
- $k = 0.5\sigma$ (allowable slack, standar untuk seri ekonomi)
- Alarm ketika $\text{CUSUM}^+ > h$ atau $\text{CUSUM}^- > h$, dengan $h = 4\sigma$ (ARL ≈ 370 false alarms)

### Perubahan di `ml/src/detect.py`

1. **Konstanta baru:**
   ```python
   CUSUM_SLACK     = 0.50   # k parameter
   CUSUM_THRESHOLD = 4.00   # h parameter
   ```

2. **Dataclass baru `CusumResult`:**
   - Field: `is_alarm`, `cusum_pos`, `cusum_neg`, `direction`, `n_baseline`

3. **Fungsi baru:**
   - `detect_changepoint_cusum(recent_prices, baseline_prices, slack, threshold)` → pure function, tidak ada state
   - `build_cusum_result(komoditas, kota, tanggal, history_df)` → convenience wrapper

4. **`DetectionResult` diperbarui:**
   - Field baru: `cusum: CusumResult | None`
   - `__post_init__` diperbarui: Z-score fire → `red`; CUSUM fire → `yellow` (early warning)
   - Dual signal (keduanya fire) → otomatis `red` via `_escalate_alert()`

5. **`run_detection()` diperbarui:**
   - Memanggil `build_cusum_result()` sebagai langkah B2, setelah Z-score (B1)

### Perubahan di `ml/src/decide.py`
- `_build_user_message()` menambahkan field: `is_cusum_alarm`, `cusum_direction`, `cusum_pos`
- `SYSTEM_PROMPT` diperbarui untuk mengajarkan agent cara menginterpretasi sinyal CUSUM

### Perubahan di `ml/src/pipeline.py`
- `to_dict()` pada `FullAnalysisResult` menambahkan `is_cusum_alarm` dan `cusum_direction` ke response API

---

## 3. Penggantian LLM Provider: OpenAI → OpenRouter

### Latar Belakang
LLM Reasoning Agent (Layer 3) sebelumnya hanya mendukung OpenAI API secara hardcoded.
Diganti ke **OpenRouter** agar fleksibel: satu key untuk akses GPT-4o, Gemini, Claude, Llama, dll.

OpenRouter kompatibel dengan OpenAI Python SDK — hanya perlu mengubah `base_url`.

### Model Default
`google/gemini-2.5-flash` — cepat, murah, sangat baik untuk structured JSON output.

### Perubahan

#### `ml/src/decide.py`
- `MODEL = "gpt-4o-mini"` → `MODEL = "google/gemini-2.5-flash"`
- `ReasoningAgent.__init__()` sekarang membaca:
  - `LLM_API_KEY` (env var, bukan `OPENAI_API_KEY`)
  - `LLM_BASE_URL` (default: `https://api.openai.com/v1`, override ke OpenRouter)
  - `LLM_MODEL` (override model via env)
- `OpenAI(api_key=..., base_url=...)` — base_url sekarang dikonfigurasi

#### `ml/serve/api.py`
- Dihapus: `OPENAI_API_KEY`
- Ditambahkan: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
- `LLM_BASE_URL` default: `https://openrouter.ai/api/v1`

#### `ml/src/pipeline.py`
- `openai_api_key` parameter diganti dengan `llm_api_key`, `llm_base_url`, `llm_model`
- `ReasoningAgent(...)` sekarang menerima `base_url` dan `model`

#### `ml/.env.example`
- Dihapus: `OPENAI_API_KEY`
- Ditambahkan:
  ```
  LLM_API_KEY=sk-or-your-openrouter-key-here
  LLM_BASE_URL=https://openrouter.ai/api/v1
  LLM_MODEL=google/gemini-2.5-flash
  ```

#### `ml/.env` (lokal)
- Ditambahkan slot `LLM_API_KEY=` (kosong, menunggu key dari user)

---

## 4. Status Akhir Sesi

### File yang Dimodifikasi
| File | Perubahan |
|---|---|
| `ml/src/features.py` | `load_from_postgres()` |
| `ml/src/detect.py` | CUSUM: `CusumResult`, `detect_changepoint_cusum()`, `build_cusum_result()`, update `DetectionResult`, `run_detection()` |
| `ml/src/decide.py` | OpenRouter: `MODEL`, `__init__()`, `_build_user_message()`, `SYSTEM_PROMPT` |
| `ml/src/pipeline.py` | LLM params rename, `from_config()`, `to_dict()` |
| `ml/serve/api.py` | Env vars: Supabase only + OpenRouter LLM |
| `ml/requirements.txt` | `psycopg2-binary`, `SQLAlchemy` |
| `ml/.env.example` | Supabase + LLM vars |
| `ml/.env` | Supabase creds + LLM slot |

### Pending
- [ ] User menyediakan OpenRouter API key → isi `LLM_API_KEY=` di `ml/.env`
- [ ] Pertimbangkan menambah Prophet sebagai algoritma forecast kedua (Layer 1) di sesi berikutnya

### Arsitektur Detection Engine (final)
```
run_detection()
├── A) HET Threshold → green / yellow / red
├── B1) Z-score (detect_changepoint_online) → sudden spike → red
├── B2) CUSUM (detect_changepoint_cusum)   → sustained drift → yellow (early warning)
│       └── dual signal (B1 + B2) → red (high confidence)
└── C) Disparity Scoring → cross-city price gap
        ↓
DetectionResult.final_alert_level = max(A, B1, B2, C)
```

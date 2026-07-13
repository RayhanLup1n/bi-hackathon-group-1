# R.A.D.A.R Pangan ? Strict $0 Infrastructure

## TLDR

Deployment target untuk MVP strict $0:

~~~text
Cloudflare Pages  ?  Frontend static
Render Free       ?  Satu FastAPI service
Neon Free         ?  PostgreSQL Gold/Serving
BigQuery Sandbox  ?  Batch warehouse terbatas
GitHub Actions    ?  Scheduled refresh dan sync
~~~

Railway dan Supabase tetap dapat dipakai selama masa migrasi, tetapi bukan lagi target deployment default. Tidak ada provider account yang diubah oleh repository ini.

## 1. Runtime Topology

### Frontend

Deploy isi folder frontend/ sebagai Cloudflare Pages static site.

File pendukung:

- frontend/_redirects ? route extensionless ke file HTML;
- frontend/config.js ? runtime API base URL dan fetch rewrite.

Sebelum deployment, ubah nilai berikut pada frontend/config.js:

~~~javascript
window.RADAR_API_BASE_URL = "https://<render-service>.onrender.com";
~~~

Jika frontend masih disajikan oleh FastAPI pada origin yang sama, biarkan nilainya kosong.

### Backend

Deploy root Dockerfile sebagai satu Render Web Service:

- Docker context: repository root;
- health check: /health;
- start command memakai $PORT;
- database memakai DB_*;
- ML service tidak wajib online.

Render Free memiliki sleep/restart dan bukan target SLA production. UX frontend harus menangani cold start serta backend unavailable state.

### Database

Neon hanya menyimpan serving data: users, harga, cuaca, hari besar, HET, predictions, decision review, dan metadata recommendation/pipeline.

Raw historical warehouse tidak boleh disalin penuh ke Neon. Gunakan BigQuery atau artifact batch untuk raw/staging.

Canonical environment variables:

~~~text
DB_HOST
DB_PORT=5432
DB_NAME=postgres
DB_USER
DB_PASSWORD
DB_SSLMODE=require
DB_STATEMENT_TIMEOUT_MS=15000
~~~

Kode masih menerima SUPABASE_* sebagai fallback compatibility selama migrasi.

## 2. Batch Data Workflow

.github/workflows/daily-data-refresh.yml menggantikan Kestra cloud untuk daily refresh:

~~~text
load_historical
  ? load_weather_historical
  ? dbt run
  ? dbt test
  ? sync_gold_to_postgres
~~~

Workflow membutuhkan GitHub secrets:

~~~text
GCP_SERVICE_ACCOUNT_JSON
DB_HOST
DB_USER
DB_PASSWORD
~~~

Variable opsional: GCP_PROJECT, BQ_LOCATION, DB_PORT, dan DB_NAME.

Workflow tidak menjalankan Kestra dan tidak menjalankan training ML.

## 3. ML Lifecycle

Training model dilakukan manual/offline:

~~~bash
python -m ml.retrain --train-end 2025-12-31 --val-end 2026-04-30
~~~

Inference cloud belum menjadi service always-on. Sampai batch inference entrypoint dan model artifact tervalidasi tersedia, aplikasi menggunakan prediction result tersimpan, rule-based HET/RCA/Bowtie, dan graceful fallback.

Jangan mengaktifkan workflow inference terjadwal sebelum artifact model binary tersedia dan persistence path diuji terhadap database target.

## 4. BigQuery Sandbox Boundary

BigQuery Sandbox hanya dipakai untuk batch warehouse terbatas. Table/view/partition memiliki expiration default dan beberapa operasi DML tidak tersedia. Dataset harus dapat dibangun ulang dari source, query harus partition-aware, dan sync Gold harus idempotent.

Jika retensi melebihi batas Sandbox, gunakan export artifact lokal yang terenkripsi atau evaluasi ulang constraint $0; jangan mengaktifkan billing secara diam-diam.


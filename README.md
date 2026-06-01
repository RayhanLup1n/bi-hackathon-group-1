# R.A.D.A.R Pangan

**Real-time Anti-inflation Detection, Analysis & Response**

Platform monitoring, prediksi, dan respons inflasi harga pangan di Indonesia. Mengintegrasikan data harga real PIHPS, kalender hari besar, data cuaca, dan prediksi ML untuk mendeteksi anomali, membandingkan harga terhadap HET, serta merekomendasikan kebijakan intervensi.

**Tim Simatana** — Hackathon PIDI (Digitalisasi Ketahanan Pangan) | **v0.7.0** | **Demo: 4 Juni 2026**

---

## Fitur Utama

- **Dashboard Monitoring** — Pantau harga harian 6 komoditas di 4 provinsi dengan 3 pilar (HET status, prediksi ML, Bowtie snapshot)
- **HET Monitor** — Bandingkan harga aktual vs Harga Eceran Tertinggi (AMAN / WASPADA / KRITIS / MELAMPAUI)
- **RCA Engine** — Root Cause Analysis 4-step sequential: hari raya, cuaca ekstrem, persebaran kota, stok pedagang
- **FTA & Bowtie Analysis** — Fault Tree Analysis (6 threats) + 12 barriers (prevention & mitigation) dengan severity L0–L4
- **Prediksi ML (3-Layer)** — LightGBM P50/P90 → Bayesian Changepoint + HET → LLM Reasoning Agent
- **Data Cuaca** — Integrasi Open-Meteo untuk deteksi pengaruh cuaca ekstrem terhadap harga
- **RBAC** — Role-based access control (Viewer, Analyst, Admin) dengan JWT authentication
- **Graceful Degradation** — Dashboard berfungsi penuh meskipun ML server offline

## Cakupan MVP

### Komoditas (6)

| Komoditas | ID |
|-----------|-----|
| Bawang Merah Ukuran Sedang | com_11 |
| Bawang Putih Ukuran Sedang | com_12 |
| Cabai Merah Besar | com_13 |
| Cabai Merah Keriting | com_14 |
| Cabai Rawit Hijau | com_15 |
| Cabai Rawit Merah | com_16 |

### Wilayah (4 Provinsi, 18 Kota)

| Provinsi | Kota | Data |
|----------|------|------|
| Banten | Tangerang, dll | 104K rows |
| Jawa Barat | Bandung, Bogor, Depok, Bekasi, Cirebon, dll | 312K rows |
| DKI Jakarta | Jakarta Pusat | 34K rows |
| Sulawesi Selatan | Makassar, dll | 167K rows |

### Sumber Data

| Sumber | Data | Jumlah |
|--------|------|--------|
| [BI PIHPS](https://www.bi.go.id/hargapangan) | Harga harian 21 komoditas | 619,430 rows |
| python-holidays | Hari libur nasional + cuti bersama | 91 rows (2024-2027) |
| [Open-Meteo](https://open-meteo.com) | Data cuaca historis | 11,605 rows |

## Arsitektur

### Tech Stack

| Layer | Teknologi |
|-------|-----------|
| Frontend | HTML + Alpine.js + Chart.js (neobrutalism design) |
| Backend | FastAPI (Python) |
| Database (Bronze + Silver) | Google BigQuery |
| Database (Gold / Serving) | PostgreSQL (Dev: Supabase, Prod: Docker) |
| ETL | Kestra v1.3.19 + dbt-bigquery |
| ML | LightGBM + Bayesian Changepoint + LLM Reasoning (teammate managed) |
| Infrastructure | Terraform (GCP), Docker Compose |
| Auth | JWT HS256 + bcrypt + RBAC |
| Deployment | Railway (demo) / Docker Compose (prod) |

### Medallion Architecture

```
Data Sources                    ETL Pipeline              Data Warehouse          Serving
-----------                    ------------              ---------------         -------
BI PIHPS (harga)    ──┐
Hari Besar          ──┼──>  Kestra + dbt  ──>  BigQuery (Bronze+Silver)  ──>  PostgreSQL (Gold)
Open-Meteo (cuaca)  ──┘                                                            |
                                                                                   v
                                                                              FastAPI Backend
                                                                                   |
                                                                              HTML + Alpine.js
```

- **BigQuery**: Bronze (raw data) + Silver (staging transforms) - untuk heavy compute batch
- **PostgreSQL**: Gold (marts + app tables) - untuk low-latency serving ke UI/API/ML

### Halaman (6)

| # | Halaman | URL | Akses Min |
|---|---------|-----|-----------|
| 1 | Login | `/login` | Semua |
| 2 | Dashboard Monitoring | `/` | Viewer+ |
| 3 | Panduan Analis | `/guide` | Semua |
| 4 | FTA & Bowtie Analysis | `/rca` | Analyst+ |
| 5 | Prediksi ML | `/prediksi` | Analyst+ |
| 6 | Admin | `/admin` | Admin |

### RCA Engine - 4 Step Sequential Check

1. **Cek Kalender Hari Raya** — Window H-14 s/d H+3 dari hari besar nasional
2. **Cek Cuaca Ekstrem** — Hujan >100mm, drought >14 hari, suhu >38C, angin >60km/h
3. **Cek Persebaran Kenaikan Antar Kota** — >60% kota naik = indikasi supply nasional
4. **Cek Stok Pedagang** — Placeholder untuk data Badan Pangan

Early exit: jika step triggered, langsung diagnosa tanpa lanjut ke step berikutnya.

### Bowtie Analysis

| Component | Detail |
|-----------|--------|
| **FTA Threats** | 6 threats: D1 (Hari Raya), D2 (Spekulasi), S1 (Cuaca), S2 (Stok), S3 (Distribusi), S4 (Impor) |
| **Prevention** | 6 barriers (P1–P6): stabilisasi stok, early warning, diversifikasi sumber, dll |
| **Mitigation** | 6 barriers (M1–M6): operasi pasar, subsidi, distribusi darurat, dll |
| **Severity** | L0 (Normal) → L1 → L2 → L3 → L4 (Kritis) |

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) (untuk BigQuery access)

### Install

```bash
# 1. Clone repo
git clone <repo-url>
cd bi-hackathon-group-1

# 2. Install dependencies
uv sync

# 3. Setup environment variables
cp .envs/.env.example .envs/.env
# Edit .envs/.env -> isi SUPABASE_PASSWORD

# 4. Setup GCP credentials (untuk BigQuery)
gcloud auth application-default login
gcloud config set project radar-pangan-hackathon
```

### Run App

```bash
# Jalankan FastAPI server
uv run uvicorn main:app --reload

# Akses di browser
# App:    http://localhost:8000
# Login:  http://localhost:8000/login
# Docs:   http://localhost:8000/docs
```

### Default Users

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin (full access) |
| analyst | analyst123 | Analyst (Dashboard + RCA + Prediksi) |

### Run Tests

```bash
uv run pytest tests/ -v
```

### Docker

```bash
# App saja (FastAPI)
docker compose up app

# App + ETL (Kestra)
docker compose --profile etl up

# App + ML
docker compose --profile ml up

# Semua services
docker compose --profile etl --profile ml up

# Build ulang
docker compose build app
```

### Kestra UI

```bash
# Akses Kestra UI di http://localhost:8080
# Login: admin@radar-pangan.local / Admin1234
```

### dbt Transformations

```bash
# Pastikan ADC sudah login: gcloud auth application-default login
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project
uv run dbt test --profiles-dir etl/dbt_project --project-dir etl/dbt_project
```

## Struktur Project

```
bi-hackathon-group-1/
├── .envs/                  <- Environment variables (gitignored)
├── config/                 <- App settings (thresholds, HET values)
├── infra/                  <- Terraform IaC (BigQuery datasets + tables)
├── etl/
│   ├── config/             <- ETL constants (province IDs, komoditas, etc.)
│   ├── flows/              <- Kestra flow definitions (YAML)
│   ├── dbt_project/        <- dbt models (BigQuery SQL)
│   ├── extractors/         <- PIHPS + Open-Meteo extractors
│   ├── loaders/            <- PostgreSQL loader
│   └── scripts/            <- Seed, migration, and utility scripts
├── frontend/
│   ├── css/style.css       <- Shared neobrutalism stylesheet
│   ├── index.html          <- Dashboard (Alpine.js)
│   ├── login.html          <- Login page
│   ├── guide.html          <- Panduan Analis
│   ├── rca.html            <- Analisis RCA (Alpine.js)
│   ├── prediksi.html       <- Prediksi ML (Alpine.js + Chart.js)
│   └── admin.html          <- User management
├── src/
│   ├── api/
│   │   ├── routes.py       <- Commodity, RCA, HET, weather endpoints
│   │   ├── auth_routes.py  <- JWT auth + RBAC
│   │   └── ml_routes.py    <- ML proxy endpoints
│   ├── data/
│   │   ├── database.py     <- PostgreSQL connection pool (Supabase)
│   │   ├── bigquery_client.py <- BigQuery client (thread-safe singleton)
│   │   ├── commodity_data.py  <- PIHPS price queries (BigQuery)
│   │   ├── weather_data.py    <- Weather queries (BigQuery)
│   │   └── auth_db.py        <- User CRUD (bcrypt + boolean flags)
│   ├── engine/
│   │   ├── rca_engine.py   <- RCA 4-step sequential check
│   │   ├── het_monitor.py  <- HET comparison engine
│   │   └── bowtie_engine.py <- FTA + Bowtie barrier analysis
│   └── models/
│       └── schemas.py      <- Pydantic models
├── tests/                  <- 181 tests (HET, RCA, Bowtie, weather, schemas, HTML E2E)
├── docs/                   <- PRD, FRD, ERD, SDA, wireframe, tech stack
├── main.py                 <- FastAPI entry point
├── pyproject.toml          <- Dependencies (uv)
├── Dockerfile              <- FastAPI container
├── docker-compose.yml      <- All services (app + ETL + ML via profiles)
├── railway.toml            <- Railway deployment config
└── Procfile                <- Railway start command
```

## Environment Variables

```bash
# .envs/.env
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>

# BigQuery (auth via ADC - no key needed for local dev)
GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2

# JWT (wajib di production - generate dengan: python -c "import secrets; print(secrets.token_urlsafe(64))")
JWT_SECRET=<secret>

# Production / Railway (optional)
# GOOGLE_CREDENTIALS_BASE64=<base64-encoded service account JSON>
# ENABLE_DOCS=true
# CORS_ORIGINS=https://your-domain.com
```

## Tim

| Anggota | Role | Fokus |
|---------|------|-------|
| Rayhan | Cloud & Backend Engineer | Pipeline, database, API, deployment |
| Teammate (ML) | AI/ML Lead | Model training, validation, predictions |
| Teammate (Product) | Product & Domain Lead | Requirements, policy context |
| Teammate (Data) | Data & Quant Analyst | Data analysis, metrics validation |

## Status

**181 tests passing** | **619K+ rows data** | **Demo-ready** | **v0.7.0**

ML integration bersifat plug-and-play (graceful degradation — dashboard tetap berfungsi tanpa ML):
- **Opsi 1**: INSERT ke `app.ml_predictions` → otomatis muncul di prediksi page
- **Opsi 2**: Jalankan inference server (port 8001) → proxy via `/api/ml/*`

### Deployment

| Environment | Platform | Docs |
|-------------|----------|------|
| Local Dev | `uv run uvicorn main:app --reload` | README ini |
| Docker | `docker compose up` | README ini |
| Cloud Demo | Railway (4 services) | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |

## Dokumentasi

| Dokumen | Lokasi |
|---------|--------|
| PRD | [`docs/prd/PRD.md`](docs/prd/PRD.md) |
| FRD | [`docs/frd/FRD.md`](docs/frd/FRD.md) |
| ERD | [`docs/erd/ERD.md`](docs/erd/ERD.md) |
| System Design | [`docs/sda/SYSTEM_DESIGN.md`](docs/sda/SYSTEM_DESIGN.md) |
| Tech Stack | [`docs/tech-stack/TECH_STACK.md`](docs/tech-stack/TECH_STACK.md) |
| Deployment | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |
| Wireframe | [`docs/wireframe/wireframe-all-pages.html`](docs/wireframe/wireframe-all-pages.html) |
| Demo Scenarios | [`docs/demo-scenarios.md`](docs/demo-scenarios.md) |

## License

Internal project - Hackathon PIDI 2026

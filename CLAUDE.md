# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**R.A.D.A.R Pangan** (Real-time Anti-inflation Detection, Analysis & Response) - platform monitoring, prediksi, dan respons inflasi harga pangan Indonesia. Integrasi data PIHPS, kalender hari besar, dan ML predictions.

**Tim**: Simatana (Hackathon PIDI - Digitalisasi Ketahanan Pangan)
**Stage**: MVP / Proof of Concept - target demo June 4, 2026
**Branch kerja**: `feat/workflow-integration` (JANGAN langsung push ke `main`)

## Architecture

### Medallion Architecture (Bronze - Silver - Gold)

- **BigQuery** = Bronze (raw.*) + Silver (staging.*) - heavy compute, batch transforms
- **PostgreSQL** = Gold (marts.* + app.*) - low-latency serving, UI/API/ML consumption

**Database deployment**:
- **Dev & Demo**: PostgreSQL via Supabase (managed, free tier)
- **Production**: PostgreSQL via Docker `postgres:16-alpine` (self-hosted)
- Code database-agnostic - connection string via env var, pure `psycopg2` driver

### High-Level System

```
DATA SOURCES: BI PIHPS (harga) | Hari Besar | Open-Meteo
                    |
        ETL Pipeline (Kestra + dbt) in Docker
                    |
    +---------------+---------------+
    |                               |
BigQuery (Bronze+Silver)    PostgreSQL (Gold)
raw.* | staging.*           marts.* | app.*
    |                               |
    +---------------+---------------+
                    |
              FastAPI Backend <---> ML Model (port 8001)
                    |
              Frontend (HTML + Alpine.js)
```

### Database Schemas

**BigQuery** (Bronze + Silver - free tier: 10 GB storage, 1 TB queries/month):
- Project: `radar-pangan-hackathon` | Region: `asia-southeast2`
- Auth: ADC via `gcloud auth application-default login`
- `raw.*`: harga_pangan (partitioned by tanggal), cuaca_harian, dim_*, hari_besar, pipeline_log
- `staging.*`: stg_harga_pangan, stg_dim_*, stg_fact_harga_pangan
- `marts.*`: mart_modelling_*, mart_dashboard_*

**PostgreSQL** (Gold - Dev: Supabase, Prod: Docker):
- `app.*`: users, het_reference, ml_predictions, komoditas_config, dashboard_harga_pangan

**IMPORTANT**: `raw.harga_pangan` has `require_partition_filter=true` - ALL queries MUST include `WHERE tanggal >= '2020-01-01'`

### ETL Pipeline

**Stack**: Kestra v1.3.19 + dbt-bigquery + Python extractors (in Docker)
**dbt SQL dialect**: BigQuery SQL (NOT PostgreSQL)

| Flow | Fungsi | Schedule |
|------|--------|----------|
| `radar_pangan_full_pipeline` | Historical data (2020-2026) | Manual trigger |
| `radar_pangan_daily` | Daily incremental update | Daily 07:00 WIB |

### Backend: FastAPI

**Engine Logic**:
1. **HET Monitor** - harga vs HET reference - AMAN/WASPADA/KRITIS/MELAMPAUI
2. **RCA Engine** - 4-step sequential check: Hari Raya - Cuaca Ekstrem - Persebaran Kota - Stok
3. **Weather Data** - query `raw.cuaca_harian` untuk RCA
4. **Bowtie Engine** - FTA threats → prevention & mitigation barriers (6 threats, 12 barriers)

**Auth**: JWT HS256 (8 jam), bcrypt, RBAC via boolean flags (is_admin/is_analyst/is_active)

### Frontend

HTML + Alpine.js, Neobrutalism design, External CSS (`frontend/css/style.css`), Mobile-first.

| Page | URL | Role Min |
|------|-----|----------|
| Login | `/login` | Semua |
| Dashboard | `/` | Viewer+ |
| Panduan Analis | `/guide` | Semua |
| FTA & Bowtie Analysis | `/rca` | Analyst+ |
| Prediksi ML | `/prediksi` | Analyst+ |
| Admin | `/admin` | Admin only |

### ML Integration

ML teammate INSERT ke `app.ml_predictions` atau jalankan inference server (port 8001) - proxy via `/api/ml/*`.

## MVP Scope

**Komoditas (6)**: Bawang Merah, Bawang Putih, Cabai Merah Besar, Cabai Merah Keriting, Cabai Rawit Hijau, Cabai Rawit Merah

**Wilayah (4 provinsi)**: Banten, Jawa Barat, DKI Jakarta, Sulawesi Selatan

**In Scope**: Real PIHPS data, HET monitoring, RCA engine, Weather (Open-Meteo), ML predictions display, Hari besar calendar, User auth + RBAC

**Out of Scope**: BMKG (no historical API), Real-time stock, React PWA, Notification system

## Setup & Commands

### First Time Setup

```bash
# 1. Install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Clone & setup
git clone <repo-url> && cd bi-hackathon-group-1
git checkout feat/workflow-integration
uv sync

# 3. Credentials
cp .envs/.env.example .envs/.env
# Edit .envs/.env - isi SUPABASE_PASSWORD

# 4. GCP (BigQuery access)
gcloud auth application-default login
gcloud config set project radar-pangan-hackathon
```

### Common Commands

```bash
# Run app
uv run uvicorn main:app --reload

# Run tests
uv run pytest tests/ -v

# Add dependency
uv add <package-name>           # production
uv add --dev <package-name>     # dev-only

# Docker
docker compose up app                    # App only
docker compose --profile etl up          # App + Kestra
docker compose --profile etl down -v     # Stop + reset

# dbt (from root, not etl/)
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project
uv run dbt test --profiles-dir etl/dbt_project --project-dir etl/dbt_project

# Terraform (BigQuery infra)
cd infra && terraform init && terraform apply && cd ..
```

**Access points**:
- App: `http://localhost:8000` | Swagger: `http://localhost:8000/docs`
- Kestra UI: `http://localhost:8080` (admin@radar-pangan.local / Admin1234)

## Environment & Secrets

```
.envs/.env              <- Supabase + GCP credentials (gitignored)
etl/.env                <- ETL-specific config (gitignored)
infra/terraform.tfvars  <- Terraform vars (gitignored)
```

Format `.envs/.env`:
```
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>
GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2
```

## Do's and Don'ts

### DO
- Selalu kerja di branch `feat/workflow-integration`, bukan `main`
- Gunakan `.env` untuk credentials - JANGAN hardcode
- Tulis test sebelum implementasi (TDD approach)
- Tanyakan dulu ke user sebelum commit: "Apakah ini bisa dijadikan checkpoint?"
- Gunakan conventional commits format
- Gunakan dbt untuk transformasi data - jangan transform di Python jika bisa di SQL
- Tulis dbt models dalam **BigQuery SQL** (BUKAN PostgreSQL SQL)
- Tambahkan `WHERE tanggal >= '2020-01-01'` saat query `raw.harga_pangan`
- Handle error gracefully di ETL (retry, logging, fallback)
- Gunakan parameterized queries - jangan string concatenation untuk SQL
- Tambahkan type hints di Python
- Gunakan external CSS file - JANGAN inline style di HTML
- Design mobile-first
- Refer ke dokumen di `docs/` untuk konteks arsitektur

### DON'T
- Commit password/secrets ke git
- Push langsung ke `main`
- Pakai SQLite untuk data baru
- Buat dummy data baru jika data real sudah tersedia
- Hardcode tanggal hari raya - gunakan `python-holidays`
- Pakai BMKG API (tidak ada historis) - pakai Open-Meteo
- Redesign frontend ke React - MVP tetap HTML + Alpine.js
- Ubah schema Gold layer tanpa koordinasi dengan ML teammate
- Tambahkan AI attribution (Co-Authored-By) di commit message
- Over-engineer - fokus ke fungsionalitas MVP
- Query `raw.harga_pangan` tanpa partition filter
- Query BigQuery langsung dari user request - UI data harus dari PostgreSQL Gold

## BigQuery SQL Patterns (dbt)

| PostgreSQL | BigQuery |
|-----------|----------|
| `column::INTEGER` | `CAST(column AS INT64)` |
| `EXTRACT(DOW FROM date)` | `EXTRACT(DAYOFWEEK FROM date)` (1=Sun) |
| `DATE_TRUNC('week', date)` | `DATE_TRUNC(date, WEEK)` |
| `BOOL_OR(expr)` | `LOGICAL_OR(expr)` |
| `column ILIKE '%x%'` | `LOWER(column) LIKE '%x%'` |
| `date + INTERVAL '14 days'` | `DATE_ADD(date, INTERVAL 14 DAY)` |
| `STDDEV(x)` | `STDDEV_SAMP(x)` |

## Team & Data Sources

| Person | Role |
|--------|------|
| Rayhan | Cloud & Backend Engineer |
| Teammate (ML) | AI/ML Lead |
| Teammate (Product) | Product & Domain Lead |
| Teammate (Data) | Data & Quant Analyst |

| Source | Data | Status |
|--------|------|--------|
| BI PIHPS | Harga 21 komoditas | 619K rows |
| python-holidays | Libur nasional | 91 rows |
| Open-Meteo | Historical weather | 11K rows |
| HET Bapanas | Harga Eceran Tertinggi | Dummy |

## Demo Readiness: READY

Platform demo-ready. ML integration plug-and-play:
- **Opsi 1**: ML INSERT ke `app.ml_predictions` - otomatis muncul di prediksi page
- **Opsi 2**: ML jalankan inference server (port 8001) - proxy via `/api/ml/*`

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**R.A.D.A.R Pangan** (Real-time Anti-inflation Detection, Analysis & Response) is a platform for monitoring, predicting, and responding to food price inflation in Indonesia. It integrates real PIHPS price data, holiday calendars, and ML predictions to detect anomalies, compare prices against HET (Harga Eceran Tertinggi), and recommend policy interventions — all in Bahasa Indonesia.

**Tim**: Simatana (Hackathon PIDI — Digitalisasi Ketahanan Pangan)
**Stage**: MVP / Proof of Concept — target demo June 4, 2026
**Branch kerja**: `feat/workflow-integration` (JANGAN langsung push ke `main`)

## Architecture

### Medallion Architecture (Bronze → Silver → Gold)

Data pipeline menggunakan **Medallion Architecture** dengan pembagian database:
- **BigQuery** = Bronze (raw.*) + Silver (staging.*) — heavy compute, batch transforms
- **PostgreSQL** = Gold (marts.* + app.*) — low-latency serving, dikonsumsi oleh UI/API/ML

**Database deployment strategy:**
- **Dev & Demo**: PostgreSQL via Supabase (managed, free tier)
- **Production**: PostgreSQL via Docker `postgres:16-alpine` (self-hosted di VPS)
- Code database-agnostic — connection string via env var, pure `psycopg2` driver

### High-Level System

```
┌─────────────────────────────────────────────────────┐
│                   DATA SOURCES                       │
│  BI PIHPS (harga)  │  Hari Besar  │  Open-Meteo     │
└────────┬───────────┴──────┬───────┴─────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────────────────────┐
│          ETL Pipeline (Kestra + dbt)                │
│          Runs in Docker (local)                      │
│          Medallion: Bronze → Silver → Gold            │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌────────────────────┐  ┌────────────────────────────┐
│  Google BigQuery   │  │  PostgreSQL (Gold)          │
│  Bronze + Silver   │  │  Dev: Supabase (managed)    │
│                    │  │  Prod: Docker postgres:16   │
│  • raw.*  (Bronze) │  │                            │
│  • staging.* (Slv) │  │  • marts.* (dashboard, ML)  │
│                    │  │  • app.* (users, HET, pred) │
└────────┬───────────┘  └─────────┬──────────────────┘
         │                        │
         └────────┬───────────────┘
                  ▼
            ┌──────────┐          ┌────────────┐
            │ FastAPI  │          │ ML Model   │
            │ Backend  │          │ (teammate) │
            └─────┬────┘          └────────────┘
                  │
            ┌─────┴──────┐
            │  Frontend  │
            │  HTML +    │
            │  Alpine.js │
            └────────────┘
```

### Database: Dual Architecture (BigQuery + PostgreSQL)

**Prinsip**: BigQuery untuk Bronze+Silver (heavy compute, batch). PostgreSQL untuk Gold (low-latency serving, UI/API/ML consumption).

**BigQuery** (Bronze + Silver — free tier: 10 GB storage, 1 TB queries/month):
- Project: `radar-pangan-hackathon`
- Region: `asia-southeast2`
- Auth: Application Default Credentials (ADC) via `gcloud auth application-default login`
- Infrastructure: Managed via Terraform (`infra/`)

```
BigQuery (Google Cloud)
│
├── raw.                              ← ETL raw extracts
│   ├── harga_pangan                  (619K+ rows, PARTITIONED BY tanggal, CLUSTERED BY comcat_id/provinsi_id/kota_id)
│   ├── cuaca_harian                  (11K rows, PARTITIONED BY tanggal, CLUSTERED BY provinsi_id)
│   ├── dim_provinsi                  (master provinsi)
│   ├── dim_kota                      (master kota)
│   ├── hari_besar                    (hari libur nasional + cuti bersama)
│   ├── inflasi_bulanan               (inflasi bulanan dummy untuk ML)
│   ├── musim_panen                   (musim panen dummy untuk ML)
│   └── pipeline_log                  (audit trail ETL runs, PARTITIONED BY started_at)
│
├── staging.                          ← dbt cleaned views (BigQuery SQL)
│   ├── stg_harga_pangan             (deduplicated, validated, enriched)
│   ├── stg_dim_komoditas            (komoditas dimension)
│   ├── stg_dim_pasar_tipe           (pasar tipe dimension)
│   ├── stg_dim_tanggal              (kalender + hari besar flags)
│   ├── stg_dim_provinsi             (provinsi dimension)
│   ├── stg_dim_kota                 (kota dimension)
│   └── stg_fact_harga_pangan        (normalized fact: FK + harga only)
│
├── marts.                            ← dbt aggregated tables (BigQuery SQL)
│   ├── mart_modelling_harga_pangan  (ML features: lag, rolling, z-score)
│   ├── mart_dashboard_harga_pangan  (daily monitoring: delta, status, alert)
│   └── mart_dashboard_ringkasan_nasional (national-level aggregations)
│
└── app.                              ← dbt denormalized table for frontend
    └── dashboard_harga_pangan        (pre-computed dashboard data)
```

**PostgreSQL** (Gold / Serving Layer — Dev: Supabase, Prod: Docker):

```
PostgreSQL (Gold Layer)
│
├── marts.                            ← dbt aggregated tables (synced from BigQuery)
│   ├── mart_dashboard_harga_pangan  (daily monitoring: delta, status, alert)
│   ├── mart_dashboard_ringkasan_nasional (national-level aggregations)
│   └── mart_modelling_harga_pangan  (ML features: lag, rolling, z-score)
│
└── app.                              ← Application-managed tables
    ├── users                         (auth: id, username, password_hash, is_admin, is_analyst, is_active, created_at)
    ├── het_reference                 (HET per komoditas per wilayah — dummy awal)
    ├── ml_predictions                (ML model output — managed by ML teammate)
    ├── komoditas_config              (mapping komoditas aktif di MVP)
    └── dashboard_harga_pangan        (pre-computed dashboard data — dbt generated)
```

**NOTE**: raw, staging, marts schemas telah di-DROP dari Supabase (data sudah di BigQuery).
Cleanup script: `etl/scripts/cleanup_supabase_schemas.py`
Gold layer tables (marts.*) akan di-sync dari BigQuery → PostgreSQL via dbt atau Python sync script.

**IMPORTANT BigQuery notes for dbt models**:
- `harga_pangan` has `require_partition_filter=true` — ALL queries MUST include `WHERE tanggal >= '2020-01-01'`
- Source-level dbt tests on `harga_pangan` are disabled (full table scan not allowed) — enforce tests at staging level
- BigQuery SQL differs from PostgreSQL: see `etl/dbt_project/models/` for syntax patterns

### ETL Pipeline

**Stack**: Kestra v1.3.19 + dbt-bigquery + Python extractors (in Docker)
**Target**: Google BigQuery (migrated from DuckDB -> Supabase PostgreSQL -> BigQuery)
**Orchestrator**: Kestra (migrated from Airflow - 2 containers vs 4)
**dbt SQL dialect**: BigQuery SQL (NOT PostgreSQL)
**dbt auth**: OAuth via Application Default Credentials (ADC)

| Flow | Fungsi | Schedule |
|------|--------|----------|
| `radar_pangan_full_pipeline` | Historical data (2020-2026) -> BigQuery -> dbt -> Supabase | Manual trigger |
| `radar_pangan_daily` | Daily incremental update -> BigQuery -> dbt -> Supabase | Daily 00:00 UTC (07:00 WIB) |

**Data sources**:
- **BI PIHPS**: Harga harian 21 komoditas, via HTTP API with XSRF token.
  - Loaded: 4 provinsi (Banten, Jabar, DKI, Sulsel) = **619,430 rows**
- **Hari Besar**: `python-holidays` package (offline, reliable) — 91 rows (2024-2027)
- **Cuaca**: Open-Meteo Historical API (gratis, data Indonesia dari 1940) — ✅ **11,605 rows loaded** (2020-2026, 5 lokasi)
  - BMKG **TIDAK DIPAKAI** (hanya forecast 3 hari, tidak ada historis)

### Backend: FastAPI

**Engine Logic** (3 modules):
1. **HET Monitor** — bandingkan harga aktual vs HET reference → status AMAN / WASPADA / KRITIS / MELAMPAUI
2. **RCA Engine** — rule-based root cause analysis (4-step sequential, early exit):
   - Check 1: Hari Raya demand window (H-14 s/d H+3)
   - Check 2: Cuaca Ekstrem dari Open-Meteo (hujan >100mm, drought >14 hari, suhu >38°C, angin >60km/h)
   - Check 3: Persebaran kenaikan antar kota (>60% kota naik = supply nasional)
   - Check 4: Stok pedagang (placeholder untuk MVP)
3. **Weather Data Layer** — query `raw.cuaca_harian` untuk RCA cuaca check

**Auth**: JWT HS256 (8 jam expire), bcrypt password hashing, RBAC via boolean flags (is_admin/is_analyst/is_active)

**Dual Database Connection**: FastAPI connects to both BigQuery (analytics/warehouse data) and Supabase PostgreSQL (auth, HET, ML predictions)

### Frontend

HTML + Alpine.js (upgrade dari vanilla JS). No build step.
Neobrutalism design system (thick black borders, offset shadows, pastel backgrounds).
CSS: External stylesheet (`frontend/css/style.css`), bukan inline `<style>`.
Responsive: Mobile-first design (smartphone → tablet → desktop).

Pages (6 total):

| # | Page | URL | Layout | Role Min |
|---|------|-----|--------|----------|
| 1 | Login | `/login` | Single form card | Semua |
| 2 | Dashboard Monitoring | `/` | Summary + HET + RCA alert + prediksi ringkas | Viewer+ |
| 3 | Panduan Analis | `/guide` | Dokumentasi interaktif (read-only) | Semua |
| 4 | Analisis RCA | `/rca` | Filter → RCA result → 4-step check → hari besar → cuaca | Analyst+ |
| 5 | Prediksi ML | `/prediksi` | Filter → summary cards → grafik → tabel prediksi | Analyst+ |
| 6 | Admin | `/admin` | Table + modal CRUD | Admin only |

### Role Access Matrix (RBAC)

| Page | Viewer | Analyst | Admin |
|------|--------|---------|-------|
| Login | ✅ | ✅ | ✅ |
| Dashboard | ✅ Read-only | ✅ Full | ✅ Full |
| Panduan Analis | ✅ | ✅ | ✅ |
| Analisis RCA | ❌ Redirect | ✅ Full | ✅ Full |
| Prediksi ML | ❌ Redirect | ✅ Full | ✅ Full |
| Admin | ❌ Redirect | ❌ Redirect | ✅ Full |

Role ditentukan oleh boolean flags di `app.users`:
- **Viewer** (`is_admin=false, is_analyst=false`): Dashboard read-only
- **Analyst** (`is_analyst=true`): Dashboard + RCA + ML Prediksi
- **Admin** (`is_admin=true`): Semua akses + kelola user

### ML Integration Contract

ML teammate meng-INSERT predictions ke tabel `app.ml_predictions`:

```sql
CREATE TABLE app.ml_predictions (
    id SERIAL PRIMARY KEY,
    komoditas_id VARCHAR NOT NULL,          -- e.g. 'cabai_merah'
    kota_id INTEGER NOT NULL,
    prediction_date DATE NOT NULL,          -- kapan prediksi dibuat
    target_date DATE NOT NULL,              -- tanggal yang diprediksi
    predicted_price DOUBLE PRECISION,       -- P50 median
    confidence_lower DOUBLE PRECISION,      -- P10 atau P5
    confidence_upper DOUBLE PRECISION,      -- P90 atau P95
    model_version VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);
```

FastAPI tinggal SELECT dari tabel ini untuk ditampilkan di dashboard.

## MVP Scope

### Komoditas Fokus (6)
1. **Bawang Merah** (com_11) — volatile, data lengkap
2. **Bawang Putih** (com_12) — volatil, demand tinggi
3. **Cabai Merah Besar** (com_13) — paling volatile
4. **Cabai Merah Keriting** (com_14) — sering melampaui HET
5. **Cabai Rawit Hijau** (com_15) — harga ekstrem
6. **Cabai Rawit Merah** (com_16) — paling mahal

### Wilayah Fokus (4 provinsi)
| Provinsi | PIHPS ID | Kota | Status Data |
|----------|----------|------|-------------|
| Banten | 11 | Tangerang, dll | ✅ 104K rows |
| Jawa Barat | 12 | Bandung, Bogor, Depok, Bekasi, Cirebon, dll | ✅ 312K rows |
| DKI Jakarta | 13 | Jakarta Pusat | ✅ 34K rows |
| Sulawesi Selatan | 26 | Makassar, dll | ✅ 167K rows |

**Coverage**: Jabodetabek (Jakarta + Bogor + Depok + Tangerang + Bekasi) + Jawa Barat + Sulawesi Selatan

### In Scope (MVP)
- Real PIHPS price data dari pipeline ETL
- HET monitoring (dummy HET data dulu, update dengan data Bapanas nanti)
- RCA engine dengan cuaca real dari Open-Meteo
- Weather data integration (Open-Meteo Historical API) ✅ LOADED
- ML predictions display (jika teammate sudah ready)
- Hari besar calendar (dynamic via python-holidays)
- User auth + RBAC
- Dashboard monitoring interaktif

### Out of Scope (MVP)
- BMKG weather data integration (tidak ada API historis — pakai Open-Meteo)
- Real-time stock data (Koperasi Desa Merah Putih)
- React PWA rebuild (tetap HTML + Alpine.js)
- Notification system (Telegram/WA/email)
- Docker deployment untuk production

## Setup & Commands

### First Time Setup (WAJIB)

Project ini menggunakan **virtual environment via `uv`**. JANGAN install ke global Python.

```bash
# 1. Install uv (jika belum)
# Windows:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone & masuk ke project
git clone <repo-url>
cd bi-hackathon-group-1
git checkout feat/workflow-integration

# 3. Setup virtual environment + install dependencies (satu perintah)
uv sync

# 4. Copy dan isi credentials
cp .envs/.env.example .envs/.env
# Edit .envs/.env → isi SUPABASE_PASSWORD (minta ke Rayhan)

# 5. Setup GCP (untuk BigQuery access)
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth application-default login
# Pastikan project benar:
gcloud config set project radar-pangan-hackathon
```

### BigQuery Infrastructure (Terraform)

```bash
# Dari root project
cd infra

# Init terraform (pertama kali)
terraform init

# Preview changes
terraform plan

# Apply changes
terraform apply

# Kembali ke root
cd ..
```

**PENTING**: Terraform state (`terraform.tfstate`) JANGAN di-commit — sudah di `.gitignore`.

### Run App

```bash
# Jalankan FastAPI server (otomatis pakai venv)
uv run uvicorn main:app --reload

# Atau aktifkan venv dulu, baru jalankan manual
# Windows:
.venv\Scripts\activate
uvicorn main:app --reload
# macOS/Linux:
source .venv/bin/activate
uvicorn main:app --reload
```

### Run Tests

```bash
uv run pytest tests/ -v
uv run pytest tests/test_rca_engine.py::test_demand_spike_hari_raya -v
```

### Tambah Dependency Baru

```bash
uv add <package-name>           # production dependency
uv add --dev <package-name>     # dev-only dependency
# JANGAN pakai pip install — agar uv.lock tetap sinkron
```

### Docker

Semua services dikelola dari **satu `docker-compose.yml` di root** (bukan di `etl/`).

```bash
# App saja (FastAPI)
docker compose up app

# App + ETL (Kestra) - gunakan profile "etl"
docker compose --profile etl up

# Build ulang setelah perubahan code
docker compose build app
docker compose --profile etl build kestra

# Stop
docker compose down

# Stop + hapus volumes (reset Kestra database)
docker compose --profile etl down -v
```

**Kestra UI**: http://localhost:8080 (login: `admin@radar-pangan.local` / `Admin1234`)

### Run dbt Transformations

```bash
# Dari root project (bukan dari etl/)
# Pastikan ADC sudah login: gcloud auth application-default login
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project
uv run dbt test --profiles-dir etl/dbt_project --project-dir etl/dbt_project
```

dbt sekarang pakai **BigQuery** (bukan PostgreSQL). Auth via ADC (Application Default Credentials).
Env vars opsional: `GCP_PROJECT` (default: `radar-pangan-hackathon`), `BQ_LOCATION` (default: `asia-southeast2`).

Access points:
- App Login: `http://localhost:8000/login`
- App Dashboard: `http://localhost:8000`
- App Guide: `http://localhost:8000/guide` (all users)
- App RCA: `http://localhost:8000/rca` (analyst+ only)
- App Prediksi: `http://localhost:8000/prediksi` (analyst+ only)
- App Admin: `http://localhost:8000/admin` (admin only)
- Swagger API docs: `http://localhost:8000/docs`
- Kestra UI: `http://localhost:8080` (when Docker ETL profile is running)

## Git Workflow

- **Branch utama kerja**: `feat/workflow-integration`
- **JANGAN** push langsung ke `main` — selalu via PR
- **Commit format**: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- **JANGAN** commit secrets (password, API keys) — gunakan `.env` files yang ada di `.gitignore`

## Environment & Secrets

```
.envs/.env              ← Supabase PostgreSQL credentials (JANGAN commit password!)
etl/.env                ← ETL-specific config (PIHPS API, delays, etc.)
infra/terraform.tfvars  ← Terraform vars (project_id, region) — gitignored
```

Format `.envs/.env` harus menggunakan `=` (bukan `:`):
```
# Supabase PostgreSQL (app.* tables only)
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>

# BigQuery (data warehouse — raw/staging/marts)
# Auth via ADC: gcloud auth application-default login
GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2
```

## Do's and Don'ts

### DO
- **DO** selalu kerja di branch `feat/workflow-integration`, bukan `main`
- **DO** gunakan `.env` untuk credentials — JANGAN hardcode
- **DO** tulis test sebelum implementasi (TDD approach)
- **DO** tanyakan dulu ke user sebelum commit: "Apakah ini bisa dijadikan checkpoint?" beserta ringkasan perubahan. Baru commit jika user approve. JANGAN auto-commit tanpa approval
- **DO** gunakan conventional commits format
- **DO** gunakan dbt untuk transformasi data — jangan transform di Python jika bisa di SQL
- **DO** tulis dbt models dalam **BigQuery SQL** (BUKAN PostgreSQL SQL)
- **DO** tambahkan `WHERE tanggal >= '2020-01-01'` saat query `raw.harga_pangan` (partition filter required)
- **DO** handle error gracefully di ETL (retry, logging, fallback)
- **DO** gunakan parameterized queries / ORM — jangan string concatenation untuk SQL
- **DO** cek apakah data sudah ada sebelum INSERT (idempotent/upsert)
- **DO** tambahkan type hints di Python
- **DO** tulis inline comments untuk logic yang tidak obvious
- **DO** gunakan external CSS file (`frontend/css/style.css`) — JANGAN inline style di HTML
- **DO** design mobile-first (smartphone → tablet → desktop)
- **DO** refer ke dokumen PRD/FRD/ERD/SDA di `docs/` untuk konteks arsitektur

### DON'T ❌
- **DON'T** commit password/secrets ke git
- **DON'T** push langsung ke `main`
- **DON'T** pakai SQLite untuk data baru
- **DON'T** buat dummy data baru jika data real sudah tersedia di pipeline
- **DON'T** hardcode tanggal hari raya — gunakan `python-holidays` package
- **DON'T** pakai BMKG API untuk data historis (tidak tersedia) — pakai Open-Meteo jika butuh cuaca historis
- **DON'T** redesign frontend ke React — MVP tetap HTML + Alpine.js
- **DON'T** ubah schema Gold layer tanpa koordinasi dengan ML teammate
- **DON'T** tambahkan AI attribution (Co-Authored-By, Generated by) di commit message
- **DON'T** over-engineer — fokus ke fungsionalitas MVP yang bisa di-demo
- **DON'T** tulis dbt SQL dengan syntax PostgreSQL (e.g. `::INT`, `ILIKE`, `BOOL_OR`, `EXTRACT(DOW)`) — gunakan BigQuery SQL
- **DON'T** query `raw.harga_pangan` tanpa partition filter — BigQuery akan error
- **DON'T** tulis inline CSS di HTML — gunakan class dari external stylesheet
- **DON'T** query BigQuery langsung dari user request — semua UI data harus dari PostgreSQL Gold layer

## Sprint Checkpoints

### Checkpoint 1: Database Foundation ✅ DONE
- [x] Fix `.env` format (`:` → `=`) + buat `.env.example`
- [x] Setup schemas di Supabase: `raw`, `staging`, `marts`, `app`
- [x] Buat tabel `app.users` (SERIAL PK, NOT NULL constraints)
- [x] Buat tabel `app.het_reference` (SERIAL PK)
- [x] Buat tabel `app.ml_predictions` (SERIAL PK, schema ready untuk ML teammate)
- [x] Buat tabel `app.komoditas_config` (SERIAL PK, UNIQUE comcat_id)
- [x] Seed 91 records hari besar (2024-2027) via `python-holidays`

### Checkpoint 2: ETL Migration ✅ DONE
- [x] Buat `etl/loaders/postgres_loader.py` (replace DuckDB loader)
- [x] Update `etl/dbt_project/profiles.yml` → PostgreSQL adapter (Supabase)
- [x] Update Dockerfile: `dbt-duckdb` → `dbt-postgres`, `psycopg2-binary`, `holidays`
- [x] Migrate dbt SQL models: DuckDB syntax → PostgreSQL syntax
- [x] Update Airflow DAGs to use PostgresLoader
- [x] Update `etl/docker-compose.yml` (remove DuckDB volume, add Supabase env)

### Checkpoint 3: Data Loading ✅ DONE
- [x] Buat staging 3NF dimensions: `stg_dim_komoditas`, `stg_dim_pasar_tipe`, `stg_dim_tanggal`, `stg_dim_provinsi`, `stg_dim_kota`
- [x] Buat staging fact: `stg_fact_harga_pangan` (normalized, FK + harga only)
- [x] Buat app dashboard table: `app.dashboard_harga_pangan` (dbt TABLE, denormalized untuk frontend)
- [x] Load historical PIHPS data: **347,550 rows** (2020-01-01 s/d 2026-05-05)
- [x] Load hari besar data: 91 rows (2024-2027)
- [x] Database size: **363 MB** (dari 500 MB limit Supabase free tier)
- [x] Run dbt staging + marts di Supabase — 11/11 models PASS
- [ ] Verify ML teammate bisa akses data

### Checkpoint 4: App Integration ✅ DONE
- [x] Buat `src/data/database.py` — shared connection pool ke Supabase
- [x] Buat `src/data/commodity_data.py` — baca harga real dari raw.harga_pangan
- [x] Buat `src/data/auth_db.py` — user management via app.users (bcrypt + CRUD)
- [x] Update `main.py` — v0.3.0, PostgreSQL pool init, load .envs/.env
- [x] Update `src/api/routes.py` — commodity + RCA + price endpoints (data real)
- [x] Test: semua endpoint 200 OK (commodities, commodity, RCA, auth login)
- [x] Default users seeded: admin/admin123, analyst/analyst123

### Checkpoint 5: Scope Revision + Weather ✅ DONE (May 9)
- [x] Revisi scope: komoditas (6 bawang+cabai), wilayah (4 provinsi), cuaca (Open-Meteo)
- [x] Discover Province IDs: Banten=11, Sulsel=26
- [x] Centralize TARGET_PROVINCE_IDS di `etl/config/constants.py`
- [x] Tambah MVP_COMCAT_IDS, WEATHER_LOCATIONS, PROVINCE_NAMES constants
- [x] Update dbt models dengan komoditas filter (mvp_comcat_ids var)
- [x] Tambah komoditas filter di `commodity_data.py` (6 MVP komoditas)
- [x] Buat `raw.cuaca_harian` DDL + index di postgres_loader.py
- [x] Buat `etl/extractors/openmeteo_extractor.py` — Open-Meteo weather API
- [x] Buat `etl/scripts/load_weather_historical.py` — weather loader + UPSERT
- [x] Load weather data: **11,605 rows** (5 lokasi, 2020-2026)
- [x] Tambah HET thresholds + weather thresholds di config/settings.py
- [x] Setup Supabase MCP (.claude/.mcp.json)
- [x] Re-run dbt dengan komoditas filter (DB size 363→242 MB)
- [x] Load PIHPS data Banten (3 kota, 104K rows) + Sulsel (5 kota, 167K rows)

### Checkpoint 6: HET Monitor + RCA Weather Integration ✅ DONE (May 9)
- [x] Build `src/data/weather_data.py` — query cuaca untuk RCA engine
- [x] Update `commodity_data.py` — replace cuaca placeholder dengan data real
- [x] Update `rca_engine.py` — rename BMKG → Open-Meteo labels
- [x] Build `src/engine/het_monitor.py` — HET comparison engine
- [x] Add HET + cuaca API endpoints di `routes.py` (replace BMKG stubs)
- [x] Remove unused BMKG Pydantic models dari schemas.py
- [x] Write tests: 14 HET tests + 7 weather tests (total 33 pass)
- [x] Bump version to v0.4.0
- [x] Fix multi-province weather check (cek cuaca semua provinsi, bukan hanya pertama)

### Checkpoint 7: Frontend + Demo Prep ✅ DONE (May 9)
- [x] Update frontend: HET badge, weather panel, Open-Meteo labels
- [x] Connect dashboard ke API baru (real data + weather + HET)
- [x] Tambah HET monitoring view di dashboard (AMAN/WASPADA/KRITIS/MELAMPAUI)
- [x] Tambah weather info di RCA display (storm icon + detail cuaca)
- [x] End-to-end testing: 4 demo scenarios verified
- [x] Demo scenario documentation (docs/demo-scenarios.md)
- [x] Upgrade frontend dari vanilla JS ke Alpine.js
- [x] Reskin frontend dari glassmorphism ke neobrutalism

### Checkpoint 8: Auth Migration + Page Planning ✅ DONE (May 9)
- [x] Migrate users table: role VARCHAR → is_admin/is_analyst/is_active booleans
- [x] Update auth_routes.py: Pydantic models, JWT payload, admin guard
- [x] Update auth_db.py: CRUD with boolean flags, _compute_role() backward compat
- [x] Update admin.html: neobrutalism + boolean checkboxes (replace role dropdown)
- [x] Run migration script on live Supabase (2 users migrated)
- [x] Plan 6 pages + role access matrix (Login, Dashboard, Guide, RCA, Prediksi ML, Admin)
- [x] 33 tests pass

### Checkpoint 9: New Pages (RCA + Prediksi ML) ✅ DONE (May 9)
- [x] Build `/rca` page — single column stacked: filter → RCA result → detail → timeline
- [x] Build `/prediksi` page — filter → summary cards → grafik → tabel prediksi
- [x] Add role guard (analyst+ only) to both pages
- [x] Add FastAPI routes to serve new HTML pages
- [x] ML predictions API endpoint (read from app.ml_predictions)
- [ ] Add navigation links between pages (header nav di index.html, admin.html)
- [ ] Integrasi Chart.js/Plotly di halaman prediksi
- [ ] End-to-end testing halaman RCA dan Prediksi ML

### Checkpoint 10: BigQuery Migration ✅ DONE (May 14)
- [x] Setup GCP project + Terraform IaC (`infra/` directory)
- [x] Provision BigQuery datasets (raw, staging, marts) + 8 raw tables via Terraform
- [x] Partitioning: `harga_pangan` by tanggal (CLUSTERED BY comcat_id/provinsi_id/kota_id)
- [x] Build `etl/scripts/migrate_to_bigquery.py` — batch migrate from Supabase to BigQuery
- [x] Migrate 631K+ rows from Supabase to BigQuery (6 tables, ~100 seconds, FREE batch load)
- [x] Rewrite `etl/dbt_project/profiles.yml` — dbt-postgres → dbt-bigquery (oauth + ADC)
- [x] Convert all 11 dbt SQL models: PostgreSQL → BigQuery SQL (9 syntax patterns)
- [x] Add partition filters (`tanggal >= '2020-01-01'`) to all queries on `raw.harga_pangan`
- [x] Remove source-level dbt tests on partitioned table (enforce at staging level)
- [x] All 11 dbt models pass, 17/17 dbt tests pass on BigQuery
- [x] Update `pyproject.toml` — add google-cloud-bigquery, pandas-gbq, dbt-bigquery

### Checkpoint 11: FastAPI Dual Connection ✅ DONE (May 14)
- [x] Create `src/data/bigquery_client.py` — BigQuery client wrapper (thread-safe singleton, timeout, error handling)
- [x] Update `src/data/commodity_data.py` — query BigQuery instead of Supabase for analytics
- [x] Update `src/data/weather_data.py` — query BigQuery instead of Supabase for weather
- [x] Keep Supabase connection for app.* tables (auth, HET, ML predictions)
- [x] End-to-end testing: all API endpoints still work with dual connection
- [x] Code review fixes: thread safety, error handling, type hints, drought multi-lokasi
- [x] 34 tests pass (14 HET + 8 weather + 12 RCA)

### Checkpoint 12: Cleanup Supabase ✅ DONE (May 14)
- [x] Cleanup Supabase — dropped raw/staging/marts schemas (only app.* remains)
- [x] Update `.envs/.env.example` with GCP env vars (GCP_PROJECT, BQ_LOCATION, JWT_SECRET)
- [x] Add cleanup script: `etl/scripts/cleanup_supabase_schemas.py`

### Checkpoint 13: Polish + Demo Prep ✅ DONE (May 16)
- [x] Navigation between pages (header nav links) - commit `2b82df7`
- [x] Chart.js integration in prediksi page (already built-in: CDN + buildPriceChart())
- [x] Update guide.html (BMKG->Open-Meteo, 6->4 checks, neobrutalism) - commit `960ded5`
- [x] Extract inline CSS -> external `frontend/css/style.css` - commit `e0e7f1e`
- [x] End-to-end testing all pages (84 tests pass) - commit `f192444`
- [ ] Proposal tahap 2 writing

### Checkpoint 14: Documentation ✅ DONE (May 16)
- [x] PRD (Product Requirements Document) -> `docs/prd/PRD.md`
- [x] FRD (Functional Requirements Document) -> `docs/frd/FRD.md`
- [x] Wireframe / HTML Prototype -> `docs/wireframe/wireframe-all-pages.html`
- [x] ERD (from scratch, UI-driven) -> `docs/erd/ERD.md`
- [x] System Design Architecture -> `docs/sda/SYSTEM_DESIGN.md`
- [x] Tech Stack Documentation -> `docs/tech-stack/TECH_STACK.md`
- [x] Medallion Architecture defined (BigQuery Bronze+Silver -> PostgreSQL Gold)
- [x] Database deployment strategy (Supabase dev/demo -> Docker PostgreSQL production)
- [x] Cross-check consistency: Guide page added to all docs, ERD arrow fixed

### Checkpoint 15: Kestra Migration (In Progress - May 22-23)
- [x] Migrate orchestrator: Airflow (4 containers) -> Kestra (2 containers)
- [x] Write Kestra Dockerfile (Python + dbt-bigquery + ETL deps in venv)
- [x] Write 2 Kestra flows YAML (full pipeline + daily pipeline)
- [x] Rewrite ETL scripts: psycopg2 (Supabase raw.*) -> BigQuery batch load (FREE)
- [x] Fix 13 Kestra migration bugs + 3 additional fixes found during testing
- [x] Fix Kestra basic-auth (email format, security path, password requirements)
- [x] Fix null harga issue (dropna before BigQuery batch load)
- [x] Remove marts dataset from Terraform (dev mode: marts only in Supabase)
- [x] Add delete_contents_on_destroy to staging dataset
- [ ] Full end-to-end pipeline test via Kestra (partial - dihentikan sementara)
- [ ] Verify all 11 steps complete successfully
- [ ] Commit all changes after testing

## Team Responsibilities

| Person | Role | Focus |
|--------|------|-------|
| Rayhan | Cloud & Backend Engineer | Data pipeline, database architecture, API, deployment |
| Teammate (ML) | AI/ML Lead | Model training, validation, predictions output |
| Teammate (Product) | Product & Domain Lead | Problem statement, requirements, policy context |
| Teammate (Data) | Data & Quant Analyst | Data analysis, metrics validation, model evaluation |

## Key Data Sources

| Source | URL | Data | Status |
|--------|-----|------|--------|
| BI PIHPS | `bi.go.id/hargapangan` | Harga 21 komoditas | ✅ **619,430 rows** (4 prov, 18 kota, 2020-2026) |
| Hari Besar | `python-holidays` package | Libur nasional + cuti bersama | ✅ **91 rows** (2024-2027) |
| Open-Meteo | `open-meteo.com` | Historical weather data | ✅ **11,605 rows** (5 lokasi, 2020-2026) |
| HET Bapanas | `bapanas.go.id` | Harga Eceran Tertinggi | 🔍 Dummy values in config |
| BMKG | `data.bmkg.go.id` | Forecast cuaca 3 hari | ❌ Skip (no historical) |

## File Structure

```
bi-hackathon-group-1/
├── .envs/
│   ├── .env                    ← Supabase + GCP credentials (gitignored)
│   └── .env.example            ← Template tanpa secrets
├── config/
│   └── settings.py             ← App thresholds & config
├── infra/                       ← Terraform IaC for BigQuery
│   ├── main.tf                 ← GCP provider + BigQuery API
│   ├── bigquery.tf             ← 2 datasets (raw, staging) + 8 raw tables
│   ├── variables.tf            ← project_id, region, bq_location
│   ├── outputs.tf              ← Output definitions
│   ├── terraform.tfvars        ← Actual values (gitignored)
│   └── terraform.tfvars.example ← Template
├── etl/
│   ├── .env                    ← ETL-specific config (gitignored)
│   ├── config/                 ← ETL settings (pydantic-settings) + constants
│   ├── dbt_project/            ← dbt models (BigQuery SQL), profiles, macros
│   ├── extractors/             ← Data extractors (PIHPS, Open-Meteo, Playwright)
│   ├── kestra/                 ← Kestra orchestrator
│   │   ├── Dockerfile          ← Custom Kestra image (Python + dbt-bigquery)
│   │   └── flows/              ← Kestra YAML flows (full + daily pipeline)
│   ├── loaders/                ← Database loaders (postgres_loader.py)
│   └── scripts/                ← Seed scripts, historical load, migration
│       ├── check_pihps_health.py   ← PIHPS API health check
│       ├── load_historical.py      ← PIHPS historical -> BigQuery batch load
│       ├── load_weather_historical.py ← Open-Meteo -> BigQuery batch load
│       ├── seed_hari_besar.py      ← python-holidays -> BigQuery
│       ├── sync_gold_to_postgres.py ← BigQuery -> Supabase gold sync
│       ├── sync_musim_panen_to_supabase.py ← Musim panen reference data
│       ├── sync_inflasi_bulanan_to_supabase.py ← Inflasi dummy data
│       ├── migrate_to_bigquery.py  ← Supabase -> BigQuery data migration
│       ├── migrate_users_boolean_flags.py ← Role -> boolean flags migration
│       └── cleanup_supabase_schemas.py ← Drop raw/staging/marts from Supabase
├── frontend/
│   ├── css/
│   │   └── style.css           ← External CSS (neobrutalism design system)
│   ├── index.html              ← Main dashboard (Alpine.js + neobrutalism)
│   ├── login.html              ← Login page (neobrutalism)
│   ├── guide.html              ← Panduan Analis (all users, read-only)
│   ├── admin.html              ← User management (boolean checkboxes)
│   ├── rca.html                ← Analisis RCA (analyst+ only)
│   ├── prediksi.html           ← Prediksi ML (analyst+ only)
│   └── debug.html              ← DB inspector
├── src/
│   ├── api/
│   │   ├── routes.py           ← Commodity + RCA + price + HET + weather endpoints
│   │   ├── auth_routes.py      ← Auth endpoints (JWT + RBAC boolean flags)
│   │   └── ml_routes.py        ← ML proxy endpoints (inference server)
│   ├── data/
│   │   ├── database.py         ← Shared PostgreSQL connection pool (Supabase — app.* only)
│   │   ├── bigquery_client.py  ← BigQuery client wrapper (thread-safe, timeout, error handling)
│   │   ├── commodity_data.py   ← Read PIHPS prices from BigQuery (filtered to 6 MVP komoditas)
│   │   ├── auth_db.py          ← User management (bcrypt + CRUD + boolean flags)
│   │   └── weather_data.py     ← Weather data from BigQuery for RCA engine
│   ├── engine/
│   │   ├── rca_engine.py       ← RCA decision tree (4-step sequential check)
│   │   └── het_monitor.py      ← HET comparison engine
│   └── models/
│       └── schemas.py          ← Pydantic models (CommodityData, CuacaInfo, etc.)
├── tests/
│   ├── test_rca_engine.py      ← RCA engine unit tests (12 tests)
│   ├── test_het_monitor.py     ← HET monitor unit tests (14 tests)
│   └── test_weather_data.py    ← Weather data unit tests (8 tests)
├── docs/                       ← Project documentation
│   ├── prd/                    ← Product Requirements Document
│   ├── frd/                    ← Functional Requirements Document
│   ├── wireframe/              ← UI wireframe / HTML prototype
│   ├── erd/                    ← Entity Relationship Diagram
│   ├── sda/                    ← System Design Architecture
│   ├── tech-stack/             ← Tech Stack Documentation
│   ├── session-log/            ← Session logs per sesi pengembangan
│   ├── demo-scenarios.md       ← Demo script
│   └── NEED_TO_FIX.md          ← Testing report + known issues
├── main.py                     ← FastAPI entry point (v0.4.0)
├── pyproject.toml              ← Dependencies (app + dev + etl groups)
├── uv.lock                     ← Locked versions for reproducibility
├── Dockerfile                  ← FastAPI app container
├── docker-compose.yml          ← All services (app + ETL via profiles)
├── .dockerignore
├── CLAUDE.md                   ← This file
└── README.md
```

**Note**: `etl/pyproject.toml` dan `etl/docker-compose.yml` sudah dihapus.
Dependencies dikelola di root `pyproject.toml`, Docker dikelola di root `docker-compose.yml`.

## Existing Code Reference

Code yang sudah ada dan statusnya:

- **RCA Engine** (`src/engine/rca_engine.py`): ✅ 4-step sequential check. Labels updated ke Open-Meteo. 34 tests pass.
- **HET Monitor** (`src/engine/het_monitor.py`): ✅ Compare harga vs HET reference → AMAN/WASPADA/KRITIS/MELAMPAUI.
- **Weather Data** (`src/data/weather_data.py`): ✅ Query BigQuery `raw.cuaca_harian` → `CuacaInfo` untuk RCA engine. Aggregates per-date for multi-location handling.
- **Schemas** (`src/models/schemas.py`): ✅ Clean — BMKG models dihapus.
- **API Routes** (`src/api/routes.py`): ✅ Real `/api/het/*`, `/api/cuaca/*`, `/api/predictions` endpoints. BMKG stubs dihapus.
- **ML Routes** (`src/api/ml_routes.py`): ✅ ML proxy endpoints (forward to inference server).
- **Auth** (`src/api/auth_routes.py`): ✅ JWT + RBAC boolean flags. is_active check. Default users: admin/admin123, analyst/analyst123.
- **Auth DB** (`src/data/auth_db.py`): ✅ Boolean flags (is_admin/is_analyst/is_active). `_compute_role()` for backward compat.
- **Database** (`src/data/database.py`): ✅ Shared PostgreSQL connection pool (Gold layer — Dev: Supabase, Prod: Docker).
- **BigQuery Client** (`src/data/bigquery_client.py`): ✅ Thread-safe singleton, 60s timeout, GoogleAPIError handling, lazy env vars. Hanya untuk Bronze+Silver queries.
- **Weather Extractor** (`etl/extractors/openmeteo_extractor.py`): ✅ Open-Meteo API extractor.
- **BigQuery Migration** (`etl/scripts/migrate_to_bigquery.py`): ✅ Batch migrate from Supabase -> BigQuery (WRITE_TRUNCATE, free).
- **Supabase Cleanup** (`etl/scripts/cleanup_supabase_schemas.py`): ✅ Drop raw/staging/marts from Supabase.
- **Historical Loader** (`etl/scripts/load_historical.py`): ✅ PIHPS -> BigQuery batch load (WRITE_APPEND, FREE). Handles null harga via dropna().
- **Weather Loader** (`etl/scripts/load_weather_historical.py`): ✅ Open-Meteo -> BigQuery batch load. Handles null required fields.
- **Holiday Seeder** (`etl/scripts/seed_hari_besar.py`): ✅ python-holidays -> BigQuery (WRITE_TRUNCATE).
- **Gold Sync** (`etl/scripts/sync_gold_to_postgres.py`): ✅ BigQuery raw -> Supabase app.* (TRUNCATE + INSERT).
- **PIHPS Health Check** (`etl/scripts/check_pihps_health.py`): ✅ Fail-fast API availability check.
- **Kestra Flows** (`etl/kestra/flows/`): ✅ 2 flows (full + daily). Process runner, BigQuery targets, dbt with --target-path.
- **Kestra Dockerfile** (`etl/kestra/Dockerfile`): ✅ Custom image kestra:v1.3.19 + Python venv + dbt-bigquery.
- **dbt Models**: ✅ All 11 models converted to BigQuery SQL. 11/11 pass, 17/17 tests pass.
- **Terraform IaC** (`infra/`): ✅ 2 datasets (raw, staging) + 8 raw tables provisioned. deletion_protection=false, delete_contents_on_destroy=true on staging.
- **Frontend Guide** (`frontend/guide.html`): ✅ Neobrutalism + vanilla JS. Konten sesuai engine: 4 checks, Open-Meteo, 5 indikator, 4 provinsi, 6 bawang+cabai.
- **Frontend Dashboard** (`frontend/index.html`): ✅ Alpine.js + neobrutalism. HET badge, weather panel, RCA widget.
- **Frontend Login** (`frontend/login.html`): ✅ Neobrutalism style.
- **Frontend Admin** (`frontend/admin.html`): ✅ Neobrutalism + boolean checkboxes (is_admin/is_analyst/is_active).
- **Frontend RCA** (`frontend/rca.html`): ✅ Alpine.js + neobrutalism. Animated 4-step RCA, filter, detail, cuaca + hari besar context.
- **Frontend Prediksi** (`frontend/prediksi.html`): ✅ Alpine.js + neobrutalism. Chart.js (historical + prediction + CI band), ML inference + DB source tabs, summary cards.
- **Frontend CSS** (`frontend/css/style.css`): ✅ External shared stylesheet. All pages link to this, page-specific overrides in inline `<style>`.
- **Tests**: ✅ 84 tests pass (48 HTML structure + 14 HET + 14 RCA + 8 weather).

### BigQuery Status (Dev Mode)

BigQuery hanya menyimpan **raw** + **staging** (managed by Terraform). **marts** tidak di-manage Terraform - dbt auto-creates jika diperlukan.

**BigQuery** (Bronze + Silver):
- **raw.harga_pangan**: 619,430 rows (4 provinsi, 18 kota, 2020-2026) — partitioned by tanggal
- **raw.cuaca_harian**: 11,605 rows (5 lokasi, 2020-2026)
- **raw.dim_provinsi**: 34 rows
- **raw.dim_kota**: 18 rows
- **raw.hari_besar**: 91 rows (2024-2027)
- **raw.pipeline_log**: 28 rows
- **raw.inflasi_bulanan**: ~174 rows (dummy, untuk ML)
- **raw.musim_panen**: 18 rows (dummy, kalender panen)
- **Storage**: ~250 MB / 10 GB free tier (2.5% used)
- **dbt models**: 11/11 pass, 17/17 tests pass

**PostgreSQL** (Gold — Dev: Supabase, Prod: Docker):
- **app.users**: 2 users (admin, analyst)
- **app.het_reference**: HET dummy data
- **app.ml_predictions**: ML teammate managed
- **app.komoditas_config**: 6 MVP komoditas
- **app.dashboard_harga_pangan**: pre-computed dashboard data (dbt)
- **marts.***: akan di-sync dari BigQuery (mart_dashboard_*, mart_modelling_*)
- **Storage**: ~50 MB (Supabase, setelah cleanup)

### BigQuery SQL Patterns (dbt)

Ketika menulis dbt models, gunakan BigQuery SQL (BUKAN PostgreSQL):

| PostgreSQL | BigQuery |
|-----------|----------|
| `column::INTEGER` | `CAST(column AS INT64)` |
| `column::NUMERIC` | `CAST(column AS NUMERIC)` |
| `EXTRACT(DOW FROM date)` | `EXTRACT(DAYOFWEEK FROM date)` (1=Sun, 7=Sat) |
| `DATE_TRUNC('week', date)` | `DATE_TRUNC(date, WEEK)` |
| `BOOL_OR(expr)` | `LOGICAL_OR(expr)` |
| `column ILIKE '%x%'` | `LOWER(column) LIKE '%x%'` |
| `date + INTERVAL '14 days'` | `DATE_ADD(date, INTERVAL 14 DAY)` |
| `date - INTERVAL '14 days'` | `DATE_SUB(date, INTERVAL 14 DAY)` |
| `STDDEV(x)` | `STDDEV_SAMP(x)` |
| `VALUES (1, 'a'), (2, 'b')` | `SELECT 1 AS col1, 'a' AS col2 UNION ALL SELECT 2, 'b'` |
| `LAG() OVER w ... WINDOW w AS (...)` | Inline: `LAG() OVER (PARTITION BY ... ORDER BY ...)` |

### Remaining Work
1. ~~Re-run dbt~~ ✅ Done (DB optimized 363->242 MB)
2. ~~Load Banten + Sulsel~~ ✅ Done (271K rows loaded)
3. ~~Alpine.js upgrade~~ ✅ Done (neobrutalism + Alpine.js)
4. ~~Users table boolean flags~~ ✅ Done (role VARCHAR -> is_admin/is_analyst/is_active)
5. ~~Build `/rca` page~~ ✅ Done (single column stacked, animated 4-step check, analyst+ guard)
6. ~~Build `/prediksi` page~~ ✅ Done (summary cards, Chart.js, prediction table, ML+DB source tabs)
7. ~~ML predictions API endpoint~~ ✅ Done (`GET /api/predictions` + `/api/ml/*` proxy)
8. ~~BigQuery infrastructure (Terraform)~~ ✅ Done (2 datasets, 8 tables)
9. ~~Data migration Supabase -> BigQuery~~ ✅ Done (631K+ rows, 6 tables)
10. ~~dbt migration to BigQuery~~ ✅ Done (11/11 models, 17/17 tests)
11. ~~FastAPI dual connection~~ ✅ Done (BigQuery for analytics, Supabase for app.*)
12. ~~Cleanup Supabase~~ ✅ Done (raw/staging/marts dropped, only app.* remains)
13. ~~Documentation (PRD/FRD/ERD/SDA/Tech Stack/Wireframe)~~ ✅ Done
14. ~~Extract inline CSS -> external `frontend/css/style.css`~~ ✅ Done (~670 lines deduplicated)
15. ~~Update guide.html (BMKG->Open-Meteo, 4 checks, neobrutalism)~~ ✅ Done
16. ~~Navigation between pages (header nav links)~~ ✅ Done (all 6 pages)
17. ~~Chart.js integration in prediksi page~~ ✅ Done (already built-in)
18. ~~End-to-end testing~~ ✅ Done (84 tests pass)
19. ~~Kestra migration (Airflow -> Kestra)~~ ✅ Done (2 flows, scripts rewritten for BigQuery)
20. Kestra full pipeline end-to-end test (in progress, partial)
21. BigQuery Gold -> PostgreSQL sync script (low priority, not needed for demo)

### Demo Readiness Status: READY
Platform sudah demo-ready. ML integration bersifat plug-and-play:
- **Opsi 1**: ML teammate INSERT ke `app.ml_predictions` -> otomatis muncul di prediksi page
- **Opsi 2**: ML teammate jalankan inference server (port 8001) -> proxy via `/api/ml/*`

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**R.A.D.A.R Pangan** (Real-time Anti-inflation Detection, Analysis & Response) is a platform for monitoring, predicting, and responding to food price inflation in Indonesia. It integrates real PIHPS price data, holiday calendars, and ML predictions to detect anomalies, compare prices against HET (Harga Eceran Tertinggi), and recommend policy interventions — all in Bahasa Indonesia.

**Tim**: Simatana (Hackathon PIDI — Digitalisasi Ketahanan Pangan)
**Stage**: MVP / Proof of Concept — target demo mid-May 2026
**Branch kerja**: `feat/workflow-integration` (JANGAN langsung push ke `main`)

## Architecture

### High-Level System

```
┌─────────────────────────────────────────────────────┐
│                   DATA SOURCES                       │
│  BI PIHPS (harga)  │  Hari Besar  │  (future: cuaca)│
└────────┬───────────┴──────┬───────┴─────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────────────────────┐
│          ETL Pipeline (Airflow + dbt)                │
│          Runs in Docker (local)                      │
│          Target: Supabase PostgreSQL                 │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│         Supabase PostgreSQL (Cloud)                  │
│         Shared by all team members                   │
│                                                      │
│  ETL schemas:          │  App schemas:                │
│  • raw.*               │  • app.users                 │
│  • staging.*           │  • app.het_reference         │
│  • marts.*             │  • app.ml_predictions        │
│                        │  • app.komoditas_config      │
└──────────┬─────────────┴─────────┬──────────────────┘
           │                       │
     ┌─────┴──────┐          ┌─────┴──────┐
     │  FastAPI   │          │ ML Model   │
     │  Backend   │          │ (teammate) │
     └─────┬──────┘          └────────────┘
           │
     ┌─────┴──────┐
     │  Frontend  │
     │  HTML +    │
     │  Alpine.js │
     └────────────┘
```

### Database: Supabase PostgreSQL

**Connection**: Credentials di `.envs/.env` (JANGAN commit password ke git)

```
PostgreSQL (Supabase Cloud)
│
├── raw.                              ← ETL raw extracts
│   ├── harga_pangan                  (harga harian dari BI PIHPS, ~347K+ rows)
│   ├── cuaca_harian                  (cuaca harian dari Open-Meteo, ~11K rows)
│   ├── dim_provinsi                  (master provinsi)
│   ├── dim_kota                      (master kota)
│   ├── hari_besar                    (hari libur nasional + cuti bersama)
│   └── pipeline_log                  (audit trail ETL runs)
│
├── staging.                          ← dbt cleaned views
│   ├── stg_harga_pangan             (deduplicated, validated, enriched)
│   └── stg_hari_besar               (categorized holidays)
│
├── marts.                            ← dbt aggregated tables
│   ├── mart_modelling_harga_pangan  (ML features: lag, rolling, z-score)
│   ├── mart_dashboard_harga_pangan  (daily monitoring: delta, status, alert)
│   └── mart_dashboard_ringkasan     (national-level aggregations)
│
└── app.                              ← Application-managed tables
    ├── users                         (auth: id, username, password_hash, is_admin, is_analyst, is_active, created_at)
    ├── het_reference                 (HET per komoditas per wilayah — dummy awal)
    ├── ml_predictions                (ML model output — managed by ML teammate)
    └── komoditas_config              (mapping komoditas aktif di MVP)
```

### ETL Pipeline

**Stack**: Airflow + dbt + Python extractors (in Docker)
**Target**: Supabase PostgreSQL (migrated from DuckDB)

| DAG | Fungsi | Schedule |
|-----|--------|----------|
| `dag_data_ready_modelling` | Historical PIHPS data → ML features | Manual trigger |
| `dag_data_ready_dashboard` | Daily PIHPS update → dashboard tables | Daily 07:00 WIB |

**Data sources**:
- **BI PIHPS**: Harga harian 21 komoditas, via HTTP API with XSRF token.
  - Loaded: 4 provinsi (Banten, Jabar, DKI, Sulsel) = **619,430 rows**
- **Hari Besar**: `python-holidays` package (offline, reliable) — 91 rows (2024-2027)
- **Cuaca**: Open-Meteo Historical API (gratis, data Indonesia dari 1940) — ✅ **11,605 rows loaded** (2020-2026, 5 lokasi)
  - BMKG **TIDAK DIPAKAI** (hanya forecast 3 hari, tidak ada historis)

### Backend: FastAPI

**Engine Logic** (3 modules):
1. **HET Monitor** — bandingkan harga aktual vs HET reference → status AMAN / WASPADA / KRITIS / MELAMPAUI
2. **RCA Engine** — rule-based root cause analysis:
   - Check 1: Hari Raya demand window (H-14 s/d H+3)
   - Check 2: Cuaca Ekstrem dari Open-Meteo (hujan >100mm, drought >14 hari, suhu >38°C, angin >60km/h)
   - Check 3: Persebaran kenaikan antar kota (>60% kota naik = supply nasional)
   - Check 4: Stok pedagang (placeholder untuk MVP)
3. **Weather Data Layer** — query `raw.cuaca_harian` untuk RCA cuaca check

**Auth**: JWT HS256 (8 jam expire), bcrypt password hashing, RBAC via boolean flags (is_admin/is_analyst/is_active)

### Frontend

HTML + Alpine.js (upgrade dari vanilla JS). No build step.
Neobrutalism design system (thick black borders, offset shadows, pastel backgrounds).

Pages (5 total):

| # | Page | URL | Layout | Role Min |
|---|------|-----|--------|----------|
| 1 | Login | `/login` | Single form card | Semua |
| 2 | Dashboard Monitoring | `/` | Single column, summary + HET + RCA widget | Viewer+ |
| 3 | Analisis RCA | `/rca` | Single column stacked: filter → RCA result → detail → timeline | Analyst+ |
| 4 | Prediksi ML | `/prediksi` | Filter → summary cards → grafik → tabel prediksi | Analyst+ |
| 5 | Admin | `/admin` | Table + modal CRUD | Admin only |

### Role Access Matrix (RBAC)

| Page | Viewer | Analyst | Admin |
|------|--------|---------|-------|
| Login | ✅ | ✅ | ✅ |
| Dashboard | ✅ Read-only | ✅ Full | ✅ Full |
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
- BigQuery/GCS migration (post-hackathon, untuk scale data warehouse)

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
```

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
docker-compose up app

# App + ETL (Airflow) — gunakan profile "etl"
docker-compose --profile etl up

# Build ulang setelah perubahan code
docker-compose build app
docker-compose --profile etl build

# Stop
docker-compose down
```

### Run dbt Transformations

```bash
# Dari root project (bukan dari etl/)
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project
uv run dbt test --profiles-dir etl/dbt_project --project-dir etl/dbt_project
```

Perlu set environment variables Supabase sebelum run dbt (atau pastikan `.envs/.env` ter-load).

Access points:
- App Login: `http://localhost:8000/login`
- App Dashboard: `http://localhost:8000`
- App RCA: `http://localhost:8000/rca` (analyst+ only)
- App Prediksi: `http://localhost:8000/prediksi` (analyst+ only)
- App Admin: `http://localhost:8000/admin` (admin only)
- Swagger API docs: `http://localhost:8000/docs`
- Airflow UI: `http://localhost:8080` (when Docker is running)

## Git Workflow

- **Branch utama kerja**: `feat/workflow-integration`
- **JANGAN** push langsung ke `main` — selalu via PR
- **Commit format**: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- **JANGAN** commit secrets (password, API keys) — gunakan `.env` files yang ada di `.gitignore`

## Environment & Secrets

```
.envs/.env              ← Supabase PostgreSQL credentials (JANGAN commit password!)
etl/.env                ← ETL-specific config (PIHPS API, delays, etc.)
```

Format `.env` harus menggunakan `=` (bukan `:`):
```
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>
```

## Do's and Don'ts

### DO ✅
- **DO** selalu kerja di branch `feat/workflow-integration`, bukan `main`
- **DO** gunakan `.env` untuk credentials — JANGAN hardcode
- **DO** tulis test sebelum implementasi (TDD approach)
- **DO** auto-commit saat fitur/fix berhasil (checkpoint)
- **DO** gunakan conventional commits format
- **DO** simpan data yang sudah normalized ke PostgreSQL (jangan raw dump)
- **DO** gunakan dbt untuk transformasi data — jangan transform di Python jika bisa di SQL
- **DO** handle error gracefully di ETL (retry, logging, fallback)
- **DO** gunakan parameterized queries / ORM — jangan string concatenation untuk SQL
- **DO** cek apakah data sudah ada sebelum INSERT (idempotent/upsert)
- **DO** tambahkan type hints di Python
- **DO** tulis inline comments untuk logic yang tidak obvious

### DON'T ❌
- **DON'T** commit password/secrets ke git
- **DON'T** push langsung ke `main`
- **DON'T** pakai SQLite untuk data baru — semua pakai Supabase PostgreSQL
- **DON'T** buat dummy data baru jika data real sudah tersedia di pipeline
- **DON'T** hardcode tanggal hari raya — gunakan `python-holidays` package
- **DON'T** pakai BMKG API untuk data historis (tidak tersedia) — pakai Open-Meteo jika butuh cuaca historis
- **DON'T** redesign frontend ke React — MVP tetap HTML + Alpine.js
- **DON'T** ubah schema `marts.*` tanpa koordinasi dengan ML teammate
- **DON'T** tambahkan AI attribution (Co-Authored-By, Generated by) di commit message
- **DON'T** over-engineer — fokus ke fungsionalitas MVP yang bisa di-demo

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
- [x] Plan 5 pages + role access matrix (Login, Dashboard, RCA, Prediksi ML, Admin)
- [x] 33 tests pass

### Checkpoint 9: New Pages (RCA + Prediksi ML) ⬜ IN PROGRESS
- [ ] Build `/rca` page — single column stacked: filter → RCA result → detail → timeline
- [ ] Build `/prediksi` page — filter → summary cards → grafik → tabel prediksi
- [ ] Add role guard (analyst+ only) to both pages
- [ ] Add FastAPI routes to serve new HTML pages
- [ ] Add navigation links between pages (header nav)
- [ ] ML predictions API endpoint (read from app.ml_predictions)

### Checkpoint 10: Architecture Upgrade (Post-hackathon) ⬜ FUTURE
- [ ] Setup BigQuery/GCS untuk data warehouse
- [ ] Migrasi data historis ke BigQuery
- [ ] Optimasi Supabase — hanya app data
- [ ] Proposal tahap 2 writing

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
│   ├── .env                    ← Supabase credentials (gitignored)
│   └── .env.example            ← Template tanpa secrets
├── config/
│   └── settings.py             ← App thresholds & config
├── etl/
│   ├── .env                    ← ETL-specific config (gitignored)
│   ├── Dockerfile              ← Airflow + dbt + Playwright image
│   ├── config/                 ← ETL settings (pydantic-settings) + constants
│   ├── dags/                   ← Airflow DAGs
│   ├── dbt_project/            ← dbt models, profiles, macros
│   ├── extractors/             ← Data extractors (PIHPS, Open-Meteo, Playwright)
│   ├── loaders/                ← Database loaders (postgres_loader.py)
│   └── scripts/                ← Seed scripts (hari besar, historical load, weather load)
├── frontend/
│   ├── index.html              ← Main dashboard (Alpine.js + neobrutalism)
│   ├── login.html              ← Login page (neobrutalism)
│   ├── admin.html              ← User management (boolean checkboxes)
│   ├── rca.html                ← TODO: Analisis RCA (analyst+ only)
│   ├── prediksi.html           ← TODO: Prediksi ML (analyst+ only)
│   └── debug.html              ← DB inspector
├── src/
│   ├── api/
│   │   ├── routes.py           ← Commodity + RCA + price + HET + weather endpoints
│   │   └── auth_routes.py      ← Auth endpoints (JWT + RBAC boolean flags)
│   ├── data/
│   │   ├── database.py         ← Shared PostgreSQL connection pool
│   │   ├── commodity_data.py   ← Read PIHPS prices (filtered to 6 MVP komoditas)
│   │   ├── auth_db.py          ← User management (bcrypt + CRUD + boolean flags)
│   │   └── weather_data.py     ← Weather data layer for RCA engine
│   ├── engine/
│   │   ├── rca_engine.py       ← RCA decision tree (4-step sequential check)
│   │   └── het_monitor.py      ← HET comparison engine
│   └── models/
│       └── schemas.py          ← Pydantic models (CommodityData, CuacaInfo, etc.)
├── tests/
│   ├── test_rca_engine.py      ← RCA engine unit tests (12 tests)
│   ├── test_het_monitor.py     ← HET monitor unit tests (14 tests)
│   └── test_weather_data.py    ← Weather data unit tests (7 tests)
├── docs/                       ← Session logs
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

- **RCA Engine** (`src/engine/rca_engine.py`): ✅ 4-step sequential check. Labels updated ke Open-Meteo. 33 tests pass.
- **HET Monitor** (`src/engine/het_monitor.py`): ✅ Compare harga vs HET reference → AMAN/WASPADA/KRITIS/MELAMPAUI.
- **Weather Data** (`src/data/weather_data.py`): ✅ Query `raw.cuaca_harian` → `CuacaInfo` untuk RCA engine.
- **Schemas** (`src/models/schemas.py`): ✅ Clean — BMKG models dihapus.
- **API Routes** (`src/api/routes.py`): ✅ Real `/api/het/*` dan `/api/cuaca/*` endpoints. BMKG stubs dihapus.
- **Auth** (`src/api/auth_routes.py`): ✅ JWT + RBAC boolean flags. is_active check. Default users: admin/admin123, analyst/analyst123.
- **Auth DB** (`src/data/auth_db.py`): ✅ Boolean flags (is_admin/is_analyst/is_active). `_compute_role()` for backward compat.
- **Commodity Data** (`src/data/commodity_data.py`): ✅ Filtered ke 6 MVP komoditas. Multi-province weather detection.
- **Weather Extractor** (`etl/extractors/openmeteo_extractor.py`): ✅ Open-Meteo API extractor.
- **Frontend Dashboard** (`frontend/index.html`): ✅ Alpine.js + neobrutalism. HET badge, weather panel, RCA widget.
- **Frontend Login** (`frontend/login.html`): ✅ Neobrutalism style.
- **Frontend Admin** (`frontend/admin.html`): ✅ Neobrutalism + boolean checkboxes (is_admin/is_analyst/is_active).
- **Tests**: ✅ 33 tests pass (14 HET + 7 weather + 12 RCA).

### Database Status
- **Total**: 242 MB / 500 MB (258 MB free)
- **raw.harga_pangan**: 619,430 rows (4 provinsi, 18 kota, 2020-2026)
- **raw.cuaca_harian**: 11,605 rows (5 lokasi, 2020-2026)
- **marts (filtered)**: 174,290 rows (6 MVP komoditas only)

### Remaining Work
1. ~~Re-run dbt~~ ✅ Done (DB optimized 363→242 MB)
2. ~~Load Banten + Sulsel~~ ✅ Done (271K rows loaded)
3. ~~Alpine.js upgrade~~ ✅ Done (neobrutalism + Alpine.js)
4. ~~Users table boolean flags~~ ✅ Done (role VARCHAR → is_admin/is_analyst/is_active)
5. Build `/rca` page — Analisis RCA (analyst+ only)
6. Build `/prediksi` page — Prediksi ML (analyst+ only, empty state if no ML data)
7. Add navigation between pages (header nav links)
8. ML predictions API endpoint
9. BigQuery migration (post-hackathon)

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
│   ├── harga_pangan                  (harga harian dari BI PIHPS, ~346K+ rows)
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
    ├── users                         (auth: id, username, password_hash, role, created_at)
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
- **BI PIHPS**: Harga harian 21 komoditas, 10 kota, 2 provinsi (Jawa Barat, DKI Jakarta). Via HTTP API with XSRF token.
- **Hari Besar**: `python-holidays` package (offline, reliable) + `apiliburnasional.vercel.app` (backup)
- **Cuaca (future)**: Open-Meteo Historical API (gratis, data Indonesia dari 1940), bukan BMKG (BMKG hanya forecast 3 hari, tidak ada historis)

### Backend: FastAPI

**Engine Logic** (2 modules):
1. **HET Monitor** — bandingkan harga aktual vs HET reference → status AMAN / WASPADA / KRITIS / MELAMPAUI
2. **RCA Engine** — rule-based root cause analysis (adapted from v0.2.0):
   - Check 1: Hari Raya demand window (H-14 s/d H+3)
   - Check 2: Disparitas harga antarwilayah (dari data real PIHPS)
   - Check 3: Tren kenaikan serempak kota (dari mart_dashboard)
   - Check 4: ML risk signal (dari app.ml_predictions)

**Auth**: JWT HS256 (8 jam expire), bcrypt password hashing, RBAC (admin/analyst/viewer)

### Frontend

HTML + Alpine.js/HTMX (upgrade dari vanilla JS). No build step.
Glassmorphism light-themed design system.

Pages:
- `/login` — Login page
- `/` — Dashboard (monitoring harga + RCA + HET status)
- `/admin` — User management (admin only)

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

### Komoditas Fokus (2-3)
1. **Cabai Merah** — paling volatile, sering melampaui HET
2. **Bawang Merah** — kedua paling volatile
3. **Beras** — staple, paling politis

*(Pilih berdasarkan kelengkapan data di pipeline)*

### In Scope (MVP)
- Real PIHPS price data dari pipeline ETL
- HET monitoring (dummy HET data dulu jika belum dapat data real)
- RCA engine adapted untuk data real
- ML predictions display (jika teammate sudah ready)
- Hari besar calendar (dynamic via python-holidays)
- User auth + RBAC
- Dashboard monitoring interaktif

### Out of Scope (MVP)
- BMKG weather data integration (tidak ada API historis yang reliable)
- Real-time stock data (Koperasi Desa Merah Putih)
- React PWA rebuild (tetap HTML + Alpine.js)
- Multi-province coverage (fokus Jawa Barat + DKI Jakarta)
- Notification system (Telegram/WA/email)
- Docker deployment untuk production

## Commands

```bash
# === App ===
pip install -r requirements.txt
uvicorn main:app --reload

# === Tests ===
pytest tests/ -v
pytest tests/test_rca_engine.py::test_demand_spike_hari_raya -v

# === ETL (Docker) ===
cd etl
docker-compose up -d                    # Start Airflow + services
docker-compose exec airflow-webserver airflow dags trigger dag_data_ready_modelling
docker-compose down                      # Stop

# === dbt ===
cd etl/dbt_project
dbt run --profiles-dir .
dbt test --profiles-dir .
```

Access points:
- App Login: `http://localhost:8000/login`
- App Dashboard: `http://localhost:8000`
- App Admin: `http://localhost:8000/admin`
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

## Sprint Checkpoints — Minggu Ini (May 6-12)

### Checkpoint 1: Database Foundation ⬜
- [ ] Fix `.env` format (`:` → `=`) + buat `.env.example`
- [ ] Setup schemas di Supabase: `raw`, `staging`, `marts`, `app`
- [ ] Buat tabel `app.users` + seed default users
- [ ] Buat tabel `app.het_reference` (dummy HET data)
- [ ] Buat tabel `app.ml_predictions` (empty, schema ready)
- [ ] Buat tabel `app.komoditas_config`

### Checkpoint 2: ETL Migration ⬜
- [ ] Buat `etl/loaders/postgres_loader.py` (replace DuckDB loader)
- [ ] Update `etl/dbt_project/profiles.yml` → PostgreSQL adapter
- [ ] Install `dbt-postgres` (replace `dbt-duckdb`)
- [ ] Migrate dbt SQL models: DuckDB syntax → PostgreSQL syntax
- [ ] Update Airflow DAGs to use PostgreSQL loader
- [ ] Update `etl/docker-compose.yml` (remove DuckDB volume, add PG env)

### Checkpoint 3: Data Loading ⬜
- [ ] Run PIHPS ETL → data landing di Supabase PostgreSQL
- [ ] Load hari besar data via `python-holidays` → `raw.hari_besar`
- [ ] Run dbt staging + marts → verify data quality
- [ ] Verify ML teammate bisa akses marts tables

### Checkpoint 4: App Integration ⬜
- [ ] Rewrite `src/data/` layer — baca dari Supabase PostgreSQL
- [ ] Update `main.py` — init PostgreSQL connection (bukan SQLite)
- [ ] Update API endpoints — serve real data
- [ ] Verify auth flow working dengan PostgreSQL
- [ ] Test API endpoints end-to-end

### Future Checkpoints (Week 2+)
- [ ] HET monitoring engine
- [ ] RCA engine adaptation untuk data real
- [ ] ML predictions integration
- [ ] Frontend upgrade (Alpine.js)
- [ ] End-to-end demo flow
- [ ] Demo preparation & polish

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
| BI PIHPS | `bi.go.id/hargapangan` | Harga 21 komoditas, 10 kota | ✅ ETL working |
| Hari Besar | `python-holidays` package | Libur nasional + cuti bersama | ✅ Ready to use |
| HET Bapanas | `bapanas.go.id` | Harga Eceran Tertinggi | 🔍 Research / dummy |
| Open-Meteo | `open-meteo.com` | Historical weather data | 📋 Future (P2) |
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
│   ├── config/
│   ├── dags/                   ← Airflow DAGs
│   ├── dbt_project/            ← dbt models & config
│   ├── extractors/             ← Data extractors (PIHPS, etc.)
│   ├── loaders/                ← Database loaders (postgres)
│   ├── scripts/                ← Seed scripts (hari besar, users)
│   ├── docker-compose.yml
│   └── requirements.txt
├── frontend/
│   ├── index.html              ← Main dashboard
│   ├── login.html              ← Login page
│   ├── admin.html              ← User management
│   └── debug.html              ← DB inspector
├── src/
│   ├── api/
│   │   ├── routes.py           ← Commodity + RCA endpoints
│   │   └── auth_routes.py      ← Auth endpoints
│   ├── data/                   ← Data access layer (PostgreSQL)
│   ├── engine/
│   │   └── rca_engine.py       ← RCA decision tree
│   └── models/
│       └── schemas.py          ← Pydantic models
├── tests/
│   └── test_rca_engine.py      ← Engine unit tests
├── main.py                     ← FastAPI entry point
├── requirements.txt            ← App dependencies
├── CLAUDE.md                   ← This file
└── README.md
```

## Existing Code Reference (v0.2.0)

Code berikut sudah ada tapi perlu di-adapt untuk arsitektur baru:

- **RCA Engine** (`src/engine/rca_engine.py`): 4-step sequential check, return early on trigger. Sudah tested (12 tests pass). Perlu adapt input dari PostgreSQL.
- **Schemas** (`src/models/schemas.py`): Pydantic models untuk CommodityData, RCAResult, etc. Perlu extend untuk HET monitoring.
- **API Routes** (`src/api/routes.py`): Endpoint definitions sudah ada. Perlu rewire data source.
- **Auth** (`src/api/auth_routes.py`): JWT + RBAC logic sudah ada. Perlu migrate dari SQLite ke PostgreSQL.
- **Frontend**: UI sudah functional. Perlu upgrade ke Alpine.js dan connect ke API baru.
- **Tests**: 12 test cases untuk RCA engine. Perlu tambah test untuk HET monitor dan data layer.

**⚠️ Data layer files (`src/data/*.py`) belum ada** — ini yang harus dibuat dari scratch untuk PostgreSQL.

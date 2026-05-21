# **R.A.D.A.R Pangan**

## Sprint Progress Report — Data Pipeline & Backend Integration

| Periode | Sprint Week 1 |
| :---- | :---- |
| **Status** | CP1-CP4 Completed |
| **Versi** | v0.3.0 |
| **Stack** | Python · FastAPI · PostgreSQL (Supabase) · dbt · Airflow · HTML/JS |
| **Dibuat** | 6 Mei 2026 |
| **Branch** | `feat/workflow-integration` |

---

# **1. Overview**

R.A.D.A.R Pangan (Real-time Anti-inflation Detection, Analysis & Response) adalah platform pemantauan inflasi pangan yang mengintegrasikan data harga real dari BI PIHPS, kalender hari besar, dan ML predictions untuk mendeteksi anomali harga, membandingkan dengan HET, dan merekomendasikan intervensi kebijakan.

Sprint ini fokus pada **migrasi arsitektur data** (DuckDB lokal → Supabase PostgreSQL cloud), **normalisasi database 3NF**, **loading data historis**, dan **integrasi FastAPI ke Supabase**.

## **Arsitektur Sistem**

| Layer | Stack | Keterangan |
| :---- | :---- | :---- |
| **Database** | Supabase PostgreSQL (cloud) | Shared oleh semua anggota tim |
| **ETL** | Python + Airflow + dbt | Extract dari BI PIHPS, transform 3NF, load ke Supabase |
| **Backend** | FastAPI + psycopg2 | Connection pool ke Supabase, serve data real |
| **Frontend** | HTML + vanilla JS (glassmorphism) | Dashboard monitoring + RCA checklist |
| **Auth** | JWT HS256 + bcrypt | RBAC: admin / analyst / viewer |
| **Infra** | Docker (app + ETL) + uv (venv) | Satu docker-compose.yml di root |

---

# **2. Data Pipeline (ETL)**

## **2.1 Migrasi: DuckDB → Supabase PostgreSQL**

Seluruh pipeline data dimigrasikan dari DuckDB (lokal di Docker) ke Supabase PostgreSQL (cloud) agar semua anggota tim bisa akses database yang sama.

| Komponen | Sebelum | Sesudah |
| :---- | :---- | :---- |
| **Database** | DuckDB (file di Docker volume) | Supabase PostgreSQL (cloud) |
| **dbt adapter** | dbt-duckdb | dbt-postgres |
| **Loader** | `duckdb_loader.py` | `postgres_loader.py` |
| **Akses** | Hanya dari Docker container | Semua tim via credentials |
| **Docker** | `etl/docker-compose.yml` (terpisah) | Root `docker-compose.yml` (konsolidasi) |

## **2.2 Data Sources**

| Source | Data | Rows | Status |
| :---- | :---- | :---- | :---- |
| **BI PIHPS** | Harga harian 21 komoditas, 10 kota, 2 provinsi | 347,550 | ✅ Loaded (2020-2026) |
| **python-holidays** | Hari libur nasional + cuti bersama Indonesia | 91 | ✅ Loaded (2024-2027) |
| **HET Bapanas** | Harga Eceran Tertinggi per komoditas | 0 | 🔍 Research / dummy |
| **BMKG** | Data cuaca historis | — | ❌ Skip (API hanya forecast 3 hari) |

## **2.3 Database Schema (3NF)**

```
Supabase PostgreSQL — 93 MB / 500 MB free tier
│
├── raw. (as-is dari API)
│   ├── harga_pangan         347,550 rows   (BIGSERIAL PK, NOT NULL)
│   ├── dim_provinsi              34 rows
│   ├── dim_kota                  10 rows
│   ├── hari_besar                91 rows
│   └── pipeline_log             14 rows
│
├── staging. (3NF normalized — dbt VIEWs, 0 MB storage)
│   ├── stg_dim_komoditas    VIEW   21 komoditas unik
│   ├── stg_dim_pasar_tipe   VIEW   4 tipe pasar
│   ├── stg_dim_tanggal      TABLE  1,655 tanggal + hari besar flags
│   ├── stg_dim_provinsi     VIEW   dari raw.dim_provinsi
│   ├── stg_dim_kota         VIEW   kota + join provinsi
│   ├── stg_fact_harga       VIEW   normalized (FK + harga only)
│   └── stg_harga_pangan     VIEW   legacy cleaned view
│
├── marts. (denormalized — dbt TABLEs, untuk ML & dashboard)
│   ├── mart_modelling       TABLE  347,550 rows (lag, rolling, z-score)
│   ├── mart_dashboard       TABLE  347,550 rows (delta, status, alert)
│   └── mart_ringkasan       TABLE   34,755 rows (national aggregation)
│
└── app. (application-managed)
    ├── users                      2 rows  (admin, analyst)
    ├── het_reference              0 rows  (schema ready)
    ├── ml_predictions             0 rows  (schema ready untuk ML teammate)
    ├── komoditas_config           0 rows  (schema ready)
    └── dashboard_harga_pangan   347,550 rows (dbt TABLE, siap frontend)
```

## **2.4 Historical Data Loading**

File: `etl/scripts/load_historical.py`

| Aspek | Detail |
| :---- | :---- |
| **Strategy** | Batch per provinsi per tahun (anti OOM) |
| **Insert method** | `execute_batch` (bulk, bukan row-by-row) |
| **Total rows** | 347,550 |
| **Duration** | 30.2 menit |
| **Rate** | 192 rows/sec |
| **Range** | 2020-01-01 s/d 2026-05-05 |
| **Coverage** | 21 komoditas × 10 kota × 1,655 hari |
| **All 14 batches** | ✅ SUCCESS |

## **2.5 dbt Models**

11/11 models passed. Semua SQL dimigrasikan dari DuckDB syntax ke PostgreSQL syntax.

| Model | Type | Rows | Waktu |
| :---- | :---- | :---- | :---- |
| stg_dim_komoditas | VIEW | — | 1.5s |
| stg_dim_kota | VIEW | — | 1.5s |
| stg_dim_pasar_tipe | VIEW | — | 1.5s |
| stg_dim_provinsi | VIEW | — | 1.5s |
| stg_dim_tanggal | TABLE | 1,655 | 1.6s |
| stg_fact_harga_pangan | VIEW | — | 1.3s |
| stg_harga_pangan | VIEW | — | 1.3s |
| mart_modelling_harga_pangan | TABLE | 347,550 | 25.5s |
| mart_dashboard_harga_pangan | TABLE | 347,550 | 26.5s |
| mart_dashboard_ringkasan_nasional | TABLE | 34,755 | 4.4s |
| app.dashboard_harga_pangan | TABLE | 347,550 | 26.6s |

---

# **3. Backend**

## **3.1 Data Layer (Baru)**

| File | Fungsi |
| :---- | :---- |
| `src/data/database.py` | Shared connection pool ke Supabase (`SimpleConnectionPool`, context manager) |
| `src/data/commodity_data.py` | Baca harga real dari `raw.harga_pangan`, NaN-safe, lazy-load komoditas map |
| `src/data/auth_db.py` | User CRUD via `app.users`, bcrypt hashing, default seed (admin/analyst) |

## **3.2 RCA Engine (Existing, Adapted)**

File: `src/engine/rca_engine.py` — Decision tree 4-step, tetap dipertahankan.

| Step | Check | Data Source | Status |
| :---- | :---- | :---- | :---- |
| **1** | Kalender Hari Raya | `raw.hari_besar` (via python-holidays) | ✅ Data real |
| **2** | Cuaca Ekstrem (BMKG) | Placeholder (MVP) | ⬜ Belum ada data |
| **3** | Persebaran Kota | `raw.harga_pangan` (naik/turun per kota) | ✅ Data real |
| **4** | Stok Pedagang | Placeholder (Normal) | ⬜ Belum ada data |

## **3.3 API Endpoints**

File: `src/api/routes.py`, `src/api/auth_routes.py`

| Method | Endpoint | Deskripsi | Status |
| :---- | :---- | :---- | :---- |
| **GET** | /api/commodities | List komoditas (string keys) | ✅ 21 items |
| **GET** | /api/commodities/detail | List komoditas + nama + comcat_id | ✅ 21 items |
| **GET** | /api/commodity/{key} | Data harga real per kota | ✅ Data PIHPS |
| **GET** | /api/rca/{key} | Jalankan RCA satu komoditas | ✅ Working |
| **GET** | /api/rca | Jalankan RCA semua komoditas | ✅ Working |
| **GET** | /api/prices/{id}/summary | Ringkasan harga terkini | ✅ Working |
| **GET** | /api/prices/{id}/history | Histori harga harian | ✅ Working |
| **POST** | /api/auth/login | Login (JWT) | ✅ Working |
| **GET** | /api/auth/me | Data user aktif | ✅ Working |
| **GET** | /api/auth/users | List users (admin only) | ✅ Working |
| **POST** | /api/auth/users | Tambah user (admin only) | ✅ Working |
| **PATCH** | /api/auth/users/{id} | Edit user (admin only) | ✅ Working |
| **DELETE** | /api/auth/users/{id} | Hapus user (admin only) | ✅ Working |
| **GET** | /api/stok/* | Placeholder (return []) | ⬜ Belum ada data |
| **GET** | /api/bmkg/* | Placeholder (return []) | ⬜ Belum ada data |

*Semua endpoint support `?sim_date=YYYY-MM-DD` untuk simulasi tanggal*

---

# **4. Frontend**

## **4.1 Dashboard Utama**

File: `frontend/index.html`

| Fitur | Status | Keterangan |
| :---- | :---- | :---- |
| Commodity selector | ✅ Working | 21 komoditas dari `/api/commodities/detail` |
| Harga + delta % | ✅ Working | Data real dari PIHPS |
| Signal grid (cuaca, kota, stok) | ✅ Partial | Cuaca & stok placeholder, kota naik real |
| Simulation date picker | ✅ Working | min=2020, max=2026, showPicker() |
| RCA checklist animasi | ✅ Working | 4-step sequential |
| Anomaly banner | ✅ Working | Threshold-based |

## **4.2 Halaman Lain**

| Halaman | File | Status |
| :---- | :---- | :---- |
| Login | `frontend/login.html` | ✅ Working (admin/admin123) |
| Admin (user management) | `frontend/admin.html` | ✅ Working |
| DB Debug | `frontend/debug.html` | ✅ Partial (stok/bmkg placeholder) |

---

# **5. Infrastructure**

## **5.1 Virtual Environment**

Project menggunakan **uv** untuk dependency management. JANGAN install ke global Python.

```bash
uv sync                              # Install semua deps
uv run uvicorn main:app --reload     # Run app
uv run pytest tests/ -v              # Run tests
```

## **5.2 Docker**

Satu `docker-compose.yml` di root mengelola semua services:

```bash
docker-compose up app                  # App saja
docker-compose --profile etl up        # App + Airflow ETL
```

## **5.3 Database Size**

| Metric | Value |
| :---- | :---- |
| Used | ~340 MB |
| Limit (free tier) | 500 MB |
| Remaining | ~160 MB |

---

# **6. Tests**

File: `tests/test_rca_engine.py` — 12 test cases, semua passed.

| # | Test Case | Coverage |
| :---- | :---- | :---- |
| 1 | test_demand_spike_hari_raya | Hari raya trigger → DEMAND |
| 2 | test_supply_cuaca_ekstrem | Cuaca trigger → SUPPLY |
| 3 | test_supply_persebaran_kota | 6/8 kota naik → SUPPLY |
| 4 | test_supply_threshold_kota_batas | Tepat 60% threshold → trigger |
| 5 | test_supply_threshold_kota_bawah | Di bawah 60% → tidak trigger |
| 6 | test_distribusi_lokal | Semua clear, stok normal → DISTRIBUSI |
| 7 | test_unknown_stok_menipis | Stok menipis → UNKNOWN |
| 8 | test_delta_pct_calculation | Kalkulasi delta % harga |
| 9 | test_anomaly_flag_above_threshold | Delta ≥ threshold → anomaly |
| 10 | test_anomaly_flag_below_threshold | Delta < threshold → normal |
| 11 | test_result_always_has_4_checks | Output selalu 4 checks |
| 12 | test_result_fields_not_empty | Fields tidak kosong |

---

# **7. Commits (13 total)**

```
de29108 chore: consolidate project structure - remove etl duplicates
c3b9d18 fix: PostgreSQL ROUND() cast and trailing comma in dbt models
4f8eb5d fix: handle NaN prices and favicon 404
015eaaf fix: improve date picker compatibility across browsers
ea434de fix: frontend commodity selector and API compatibility
8ffaa0c feat: add Docker setup and fix 404 placeholder routes
ff000c3 chore: setup virtual environment with uv
2e8fddb docs: update CLAUDE.md with CP4 completion
033acf1 feat: connect FastAPI to Supabase PostgreSQL (CP4)
7aeea93 docs: add session log and update CLAUDE.md
8444003 feat: add historical data loading script with batching
76f8a63 feat: add 3NF staging dimensions, fact table, and app dashboard table
99b77e7 refactor: migrate ETL pipeline from DuckDB to Supabase PostgreSQL
```

---

# **8. Sprint Checkpoint Status**

| CP | Task | Status |
| :---- | :---- | :---- |
| **CP1** | Database Foundation — schemas + tables di Supabase | ✅ Done |
| **CP2** | ETL Migration — DuckDB → Supabase PostgreSQL | ✅ Done |
| **CP3** | Data Loading — 347K rows PIHPS + hari besar + dbt run | ✅ Done |
| **CP4** | App Integration — FastAPI reads from Supabase | ✅ Done |
| **CP5** | HET Monitor + RCA Adaptation | ⬜ Next |
| **CP6** | Frontend Upgrade + Demo Prep | ⬜ Pending |

---

# **9. TODO — Next Sprint**

| # | Item | Keterangan |
| :---- | :---- | :---- |
| **1** | HET monitoring engine | Bandingkan harga aktual vs HET, status AMAN/WASPADA/KRITIS |
| **2** | Adapt RCA engine untuk data real | Hari besar dari DB, disparitas dari marts |
| **3** | ML predictions integration | `app.ml_predictions` schema ready, koordinasi dengan ML teammate |
| **4** | Frontend upgrade ke Alpine.js | Interaktivitas lebih baik tanpa full React rebuild |
| **5** | End-to-end demo preparation | Skenario demo, data validation, polish UI |
| **6** | Share Supabase credentials ke tim | ML teammate butuh akses untuk training |

---

# **10. Struktur File**

| File | Fungsi |
| :---- | :---- |
| `main.py` | Entrypoint FastAPI v0.3.0 |
| `pyproject.toml` | Dependencies (app + dev + etl groups) via uv |
| `Dockerfile` | FastAPI app container |
| `docker-compose.yml` | All services (app + ETL via profiles) |
| `config/settings.py` | Threshold & URL API |
| `src/api/routes.py` | REST API endpoints (commodity + RCA + prices) |
| `src/api/auth_routes.py` | Auth endpoints (JWT + RBAC) |
| `src/data/database.py` | PostgreSQL connection pool |
| `src/data/commodity_data.py` | Data komoditas dari Supabase |
| `src/data/auth_db.py` | User management (bcrypt + CRUD) |
| `src/engine/rca_engine.py` | Decision tree logic — rule engine utama |
| `src/models/schemas.py` | Pydantic schemas / data models |
| `etl/loaders/postgres_loader.py` | PostgreSQL loader + DDL semua tabel |
| `etl/scripts/load_historical.py` | Batch historical data loader |
| `etl/scripts/seed_hari_besar.py` | Hari besar seeder via python-holidays |
| `etl/dbt_project/` | dbt models (staging 3NF + marts + app dashboard) |
| `etl/dags/` | Airflow DAGs (modelling + dashboard) |
| `etl/extractors/` | PIHPS data extractor (HTTP + Playwright fallback) |
| `frontend/index.html` | Dashboard utama RCA |
| `frontend/login.html` | Login page |
| `frontend/admin.html` | User management (admin only) |
| `frontend/debug.html` | DB inspector |
| `tests/test_rca_engine.py` | 12 unit tests pytest |
| `docs/` | Session logs & progress reports |

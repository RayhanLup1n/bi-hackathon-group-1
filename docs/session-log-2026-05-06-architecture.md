# Session Log — Arsitektur & Data Pipeline Migration

**Tanggal:** 6 Mei 2026 (evening session)  
**Branch:** `feat/workflow-integration`  
**Dikerjakan oleh:** Rayhan + Claude AI

---

## Ringkasan

Session ini fokus pada **alignment arsitektur**, **migrasi ETL dari DuckDB ke Supabase PostgreSQL**, **normalisasi database 3NF**, dan **loading data historis PIHPS** (2020-2026). Seluruh data pipeline sekarang terhubung ke Supabase cloud sehingga semua anggota tim bisa mengakses database yang sama.

---

## Keputusan Arsitektur yang Disepakati

### 1. Database: Supabase PostgreSQL (Cloud)
- **Alasan**: Semua anggota tim perlu akses ke data yang sama. DuckDB lokal di Docker hanya bisa diakses oleh satu orang.
- **Connection**: Via Supavisor pooler (`aws-1-ap-northeast-1.pooler.supabase.com:6543`)
- **Free tier**: 500 MB — estimasi penggunaan ~330 MB (muat)

### 2. Schema Architecture: Raw → Staging (3NF) → Marts → App
- **Raw**: Data as-is dari API (denormalized) — source of truth mentah
- **Staging**: Normalized 3NF via dbt VIEWs (0 MB storage) — dim tables + fact table
- **Marts**: Denormalized TABLEs untuk ML training (dbt managed)
- **App**: Application tables (users, HET, predictions, dashboard)

### 3. Komoditas Fokus MVP: Cabai Merah, Bawang Merah, Beras
- Dipilih berdasarkan volatilitas dan relevansi dengan proposal

### 4. Frontend: HTML + Alpine.js (bukan React)
- Untuk MVP 2 minggu, rebuild ke React tidak realistis

### 5. Engine: Keep RCA + Tambah HET Monitoring
- RCA engine existing dipertahankan dan di-adapt untuk data real
- HET monitoring ditambahkan sebagai fitur baru

### 6. BMKG: Skip untuk MVP
- API BMKG hanya menyediakan forecast 3 hari, tidak ada data historis
- Alternatif future: Open-Meteo Historical API

### 7. Hari Besar: python-holidays package
- Offline, reliable, support bahasa Indonesia
- Include cuti bersama via `categories=('government',)`

---

## Yang Dikerjakan

### CP1: Database Foundation ✅
- Setup 4 schema di Supabase: `raw`, `staging`, `marts`, `app`
- Buat tabel raw: `harga_pangan` (BIGSERIAL PK), `dim_provinsi`, `dim_kota`, `pipeline_log`, `hari_besar`
- Buat tabel app: `users`, `het_reference`, `ml_predictions`, `komoditas_config`
- Semua tabel dengan auto-increment ID dan NOT NULL constraints yang proper
- Buat `.envs/.env.example` sebagai template credentials
- Seed 91 records hari besar (2024-2027) via `python-holidays`

### CP2: ETL Migration (DuckDB → PostgreSQL) ✅
- Buat `etl/loaders/postgres_loader.py` — pengganti `duckdb_loader.py`
- Update `profiles.yml`: DuckDB adapter → PostgreSQL adapter (Supabase)
- Update `Dockerfile`: `dbt-duckdb` → `dbt-postgres`, tambah `psycopg2-binary` + `holidays`
- Migrate `stg_harga_pangan.sql`: `SELECT * EXCLUDE(rn)` → explicit columns (PG compatible)
- Update kedua DAGs: semua `DuckDBLoader` → `PostgresLoader`
- Update `docker-compose.yml`: hapus DuckDB volume, tambah Supabase env vars
- Update `config/settings.py`: tambah Supabase connection fields

### CP3: Data Loading ✅
- **Normalisasi 3NF** — buat 6 staging models baru:
  - `stg_dim_komoditas` (VIEW) — unique komoditas dari raw
  - `stg_dim_pasar_tipe` (VIEW) — static 4 tipe pasar
  - `stg_dim_tanggal` (TABLE) — date dimension + hari besar flags + window hari raya
  - `stg_dim_provinsi` (VIEW) — dari raw.dim_provinsi
  - `stg_dim_kota` (VIEW) — kota + join provinsi
  - `stg_fact_harga_pangan` (VIEW) — normalized fact (FK + harga only)
- **App dashboard table** — `app.dashboard_harga_pangan` (dbt TABLE):
  - Denormalized, JOIN semua dimensions + pre-computed metrics
  - Satu tabel khusus untuk frontend, siap query tanpa JOIN
- **Historical data loading**:
  - Buat `scripts/load_historical.py` — batch per provinsi per tahun
  - Bulk INSERT via `execute_batch` (bukan row-by-row)
  - **347,550 rows loaded** dalam 30 menit (192 rows/sec)
  - Range: 2020-01-01 s/d 2026-05-05
  - 21 komoditas × 10 kota × 1,655 hari
  - Database size: 93 MB (dari 500 MB limit)
- Register `raw.hari_besar` sebagai dbt source
- Update `dbt_project.yml` dengan app schema config

---

## Data yang Ada di Database

| Tabel | Rows | Size | Keterangan |
|-------|------|------|------------|
| `raw.harga_pangan` | 347,550 | 82 MB | Harga harian 2020-2026 |
| `raw.dim_provinsi` | 34 | 32 KB | 34 provinsi Indonesia |
| `raw.dim_kota` | 10 | 32 KB | 10 kota (Jabar + DKI) |
| `raw.hari_besar` | 91 | 48 KB | Libur nasional 2024-2027 |
| `raw.pipeline_log` | 14 | 48 KB | All 14 batches SUCCESS |
| `app.*` | 0 | — | Belum diisi (menunggu CP4) |
| **Total** | **347,699** | **93 MB** | |

---

## File yang Dibuat/Diubah

### Baru
- `etl/loaders/postgres_loader.py` — PostgreSQL loader + DDL semua tabel
- `etl/scripts/load_historical.py` — Batch historical data loader
- `etl/scripts/seed_hari_besar.py` — Hari besar seeder via python-holidays
- `etl/dbt_project/models/staging/stg_dim_komoditas.sql`
- `etl/dbt_project/models/staging/stg_dim_pasar_tipe.sql`
- `etl/dbt_project/models/staging/stg_dim_tanggal.sql`
- `etl/dbt_project/models/staging/stg_dim_provinsi.sql`
- `etl/dbt_project/models/staging/stg_dim_kota.sql`
- `etl/dbt_project/models/staging/stg_fact_harga_pangan.sql`
- `etl/dbt_project/models/app/dashboard_harga_pangan.sql`
- `.envs/.env.example`

### Diubah
- `etl/dbt_project/profiles.yml` — DuckDB → PostgreSQL
- `etl/dbt_project/dbt_project.yml` — tambah app schema
- `etl/dbt_project/models/staging/sources.yml` — tambah hari_besar source
- `etl/dbt_project/models/staging/stg_harga_pangan.sql` — PG syntax
- `etl/dbt_project/macros/generate_schema_name.sql` — update comment
- `etl/dags/dag_data_ready_modelling.py` — DuckDBLoader → PostgresLoader
- `etl/dags/dag_data_ready_dashboard.py` — DuckDBLoader → PostgresLoader
- `etl/docker-compose.yml` — hapus DuckDB volume, tambah Supabase env
- `etl/Dockerfile` — dbt-duckdb → dbt-postgres
- `etl/config/settings.py` — tambah Supabase fields
- `etl/.env.example` — tambah Supabase section
- `CLAUDE.md` — full rewrite arsitektur + checkpoints

### Deprecated (tidak dihapus, untuk referensi)
- `etl/loaders/duckdb_loader.py` — digantikan postgres_loader.py

---

## Commits

```
8444003 feat: add historical data loading script with batching
76f8a63 feat: add 3NF staging dimensions, fact table, and app dashboard table
99b77e7 refactor: migrate ETL pipeline from DuckDB to Supabase PostgreSQL
```

---

## Next Steps (CP4+)

1. **CP4: App Integration** — Rewrite FastAPI data layer untuk baca dari Supabase PostgreSQL
2. **CP5: HET Monitor + RCA** — Build HET monitoring engine + adapt RCA untuk data real
3. **CP6: Frontend + Demo** — Upgrade ke Alpine.js, connect API baru, demo prep
4. **dbt run** — Jalankan staging views + marts + app dashboard di Supabase (butuh Docker atau dbt lokal)
5. **Koordinasi tim** — Share schema `app.ml_predictions` ke ML teammate untuk output predictions

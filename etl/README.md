# ETL Pipeline - Harga Pangan BI PIHPS

Pipeline data harga pangan dari portal **BI PIHPS** (Bank Indonesia - Pusat Informasi Harga Pangan Strategis) untuk kebutuhan **modelling deteksi inflasi** dan **dashboard monitoring harga**.

**Sumber Data:** https://www.bi.go.id/hargapangan  
**Stack:** Apache Airflow 2.9.2 · DuckDB · dbt-core · Python 3.11 · Docker

---

## Daftar Isi

- [Arsitektur](#arsitektur)
- [Struktur Folder](#struktur-folder)
- [Quick Start](#quick-start)
- [Pipeline](#pipeline)
  - [DAG 1: data_ready_modelling](#dag-1-data_ready_modelling)
  - [DAG 2: data_ready_dashboard](#dag-2-data_ready_dashboard)
- [Skema Database (DuckDB)](#skema-database-duckdb)
- [Cara Akses Data](#cara-akses-data)
- [Data Dictionary](#data-dictionary)
- [Konfigurasi](#konfigurasi)
- [Troubleshooting](#troubleshooting)

---

## Arsitektur

```
                   BI PIHPS API
                  (bi.go.id/hargapangan)
                        │
                        │  HTTP + XSRF Token
                        ▼
              ┌───────────────────┐
              │   PihpsExtractor  │   Python — extract per kota
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │   DuckDB (raw)    │   Upsert — skip duplikat
              │   pihps.duckdb    │
              └────────┬──────────┘
                       │
                       ▼  dbt
              ┌───────────────────┐
              │ staging (VIEW)    │   Cleaning, type cast, deduplikasi
              │ stg_harga_pangan  │
              └────────┬──────────┘
                       │
            ┌──────────┴──────────────┐
            ▼                         ▼
  ┌──────────────────┐    ┌──────────────────────────┐
  │ marts (TABLE)    │    │ marts (TABLE)             │
  │ ML Features:     │    │ Dashboard:                │
  │ - lag, rolling   │    │ - delta harga, status     │
  │ - z-score        │    │ - benchmark nasional      │
  │ - calendar flags │    │ - alert harga tinggi      │
  └──────────────────┘    │                            │
                          │ Ringkasan Nasional:        │
                          │ - agregasi per komoditas   │
                          │ - distribusi status kota   │
                          └──────────────────────────┘
```

---

## Struktur Folder

```
etl/
├── config/
│   ├── settings.py              # Konfigurasi (env vars, path, dll)
│   └── constants.py             # Komoditas IDs, endpoint API
├── dags/
│   ├── dag_data_ready_modelling.py   # DAG 1: historical + ML features
│   └── dag_data_ready_dashboard.py   # DAG 2: daily dashboard
├── extractors/
│   ├── pihps_extractor.py       # Logic extraction dari API PIHPS
│   ├── http_client.py           # HTTP client dengan retry & XSRF
│   ├── playwright_scraper.py    # Fallback: headless browser
│   └── models.py                # Pydantic models (validasi data)
├── loaders/
│   └── duckdb_loader.py         # Schema init + upsert ke DuckDB
├── dbt_project/
│   ├── dbt_project.yml          # Config dbt
│   ├── profiles.yml             # Connection profile ke DuckDB
│   ├── macros/
│   │   └── generate_schema_name.sql
│   ├── models/
│   │   ├── staging/
│   │   │   └── stg_harga_pangan.sql
│   │   └── marts/
│   │       ├── modelling/
│   │       │   └── mart_modelling_harga_pangan.sql
│   │       └── dashboard/
│   │           ├── mart_dashboard_harga_pangan.sql
│   │           └── mart_dashboard_ringkasan_nasional.sql
│   └── seeds/                   # (reserved)
├── scripts/
│   ├── generate_keys.py         # Generate Airflow Fernet & Secret key
│   └── discover_endpoints.py    # Discover endpoint API PIHPS
├── tests/                       # Unit tests
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── .dockerignore
```

---

## Quick Start

### 1. Setup Environment

```bash
cd etl

# Copy template environment
cp .env.example .env
```

### 2. Generate Airflow Keys

```bash
# Jika belum install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Generate keys
uv run python scripts/generate_keys.py
```

Salin output `FERNET_KEY` dan `SECRET_KEY` ke file `.env`.

### 3. Build & Jalankan Docker

```bash
# Build image
docker compose build

# Jalankan semua service
docker compose up -d

# Cek status (pastikan semua healthy)
docker compose ps
```

### 4. Akses Airflow UI

Buka http://localhost:8080

| Field    | Value   |
|----------|---------|
| Username | `admin` |
| Password | `admin` |

### 5. Jalankan Pipeline

1. **DAG `data_ready_modelling`** — Trigger manual dari UI (tombol Play ▶)
   - Proses pertama kali: ~25-30 menit (tarik data 2020 - sekarang)
   - Proses selanjutnya: incremental, hanya data baru
2. **DAG `data_ready_dashboard`** — Otomatis setiap hari 07:00 WIB
   - Atau trigger manual untuk testing

---

## Pipeline

### DAG 1: `data_ready_modelling`

**Tujuan:** Menyiapkan dataset historis untuk training model ML deteksi inflasi  
**Schedule:** Manual trigger (pertama kali full load, selanjutnya incremental)  
**Output:** `marts.mart_modelling_harga_pangan`

```
init_schema ──▶ extract_master_data ──▶ extract_harga_historis ──▶ dbt_run_staging ──▶ dbt_run_mart ──▶ dbt_test ──▶ log_summary
```

| Task | Deskripsi |
|------|-----------|
| `init_schema` | Buat schema `raw`, `staging`, `marts` dan tabel-tabel di DuckDB |
| `extract_master_data` | Tarik data master provinsi & kota dari API PIHPS |
| `extract_harga_historis` | Tarik data harga per kota, dari 2020-01-01 hingga hari ini (incremental via checkpoint) |
| `dbt_run_staging` | Jalankan model staging: cleaning, type cast, deduplikasi |
| `dbt_run_mart` | Jalankan model mart: hitung lag, rolling stats, z-score, calendar features |
| `dbt_test` | Validasi kualitas data (warn only, tidak gagalkan DAG) |
| `log_summary` | Catat summary run ke `raw.pipeline_log` |

**Cakupan Data:**
- **Provinsi:** Jawa Barat (ID=12), DKI Jakarta (ID=13)
- **Kota:** 10 kota (Bandung, Bekasi, Bogor, Cirebon, Kab. Cirebon, Depok, Sukabumi, Kab. Tasikmalaya, Tasikmalaya, Jakarta Pusat)
- **Komoditas:** 21 komoditas strategis (beras, ayam, daging sapi, telur, bawang, cabai, minyak goreng, gula)
- **Rentang:** 2020-01-01 sampai hari ini (~346,000+ records)

---

### DAG 2: `data_ready_dashboard`

**Tujuan:** Update data harian (D-1) untuk monitoring dashboard harga pangan  
**Schedule:** Setiap hari jam 00:00 UTC (07:00 WIB)  
**Output:** `marts.mart_dashboard_harga_pangan` + `marts.mart_dashboard_ringkasan_nasional`

```
init_schema ──▶ check_source ──▶ extract_harga_harian ──▶ dbt_run_staging ──▶ dbt_run_mart ──▶ dbt_test ──▶ log_summary
```

| Task | Deskripsi |
|------|-----------|
| `init_schema` | Buat schema jika belum ada |
| `check_source` | Health check ke PIHPS API (fail-fast jika down) |
| `extract_harga_harian` | Tarik data harga kemarin (D-1) per kota |
| `dbt_run_staging` | Staging transformation |
| `dbt_run_mart` | Hitung delta harga, status, alert, benchmark nasional |
| `dbt_test` | Validasi data |
| `log_summary` | Catat summary run |

---

## Skema Database (DuckDB)

File database: `/opt/airflow/data/pihps.duckdb` (di dalam container)  
Volume Docker: `pihps-duckdb`

```
pihps.duckdb
│
├── raw                              ← Python loader
│   ├── harga_pangan                 (fact table, ~346K+ rows)
│   ├── dim_provinsi                 (2 provinsi)
│   ├── dim_kota                     (10 kota)
│   └── pipeline_log                 (audit trail)
│
├── staging                          ← dbt VIEW
│   └── stg_harga_pangan            (cleaned, deduplicated)
│
└── marts                            ← dbt TABLE
    ├── mart_modelling_harga_pangan  (ML-ready features)
    ├── mart_dashboard_harga_pangan  (per kota, daily monitoring)
    └── mart_dashboard_ringkasan_nasional  (agregasi nasional)
```

---

## Cara Akses Data

DuckDB adalah database file-based, jadi ada beberapa cara untuk mengakses datanya.

### Opsi 1: Query langsung via Docker (CLI)

Cara tercepat, langsung query dari dalam container:

```bash
# Masuk ke shell DuckDB di dalam container
docker exec -it pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb
```

Contoh query:

```sql
-- Lihat daftar tabel
SHOW ALL TABLES;

-- Preview data modelling
SELECT * FROM marts.mart_modelling_harga_pangan LIMIT 10;

-- Preview data dashboard
SELECT * FROM marts.mart_dashboard_harga_pangan LIMIT 10;

-- Cek jumlah record per tabel
SELECT 'raw' AS layer, COUNT(*) AS rows FROM raw.harga_pangan
UNION ALL
SELECT 'staging', COUNT(*) FROM staging.stg_harga_pangan
UNION ALL
SELECT 'mart_modelling', COUNT(*) FROM marts.mart_modelling_harga_pangan
UNION ALL
SELECT 'mart_dashboard', COUNT(*) FROM marts.mart_dashboard_harga_pangan;

-- Lihat harga beras di Bandung minggu ini
SELECT tanggal, komoditas_nama, harga_aktual, delta_harga_1d, pct_change_1d
FROM marts.mart_modelling_harga_pangan
WHERE kota_nama ILIKE '%bandung%'
  AND komoditas_nama ILIKE '%beras%'
ORDER BY tanggal DESC
LIMIT 7;

-- Keluar dari DuckDB CLI
.exit
```

### Opsi 2: Export ke CSV / Parquet

Export data dari dalam container lalu copy ke mesin lokal:

```bash
# Export mart modelling ke CSV
docker exec pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb \
  -c "COPY marts.mart_modelling_harga_pangan TO '/opt/airflow/data/mart_modelling.csv' (HEADER, DELIMITER ',');"

# Export mart dashboard ke Parquet (lebih efisien untuk data besar)
docker exec pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb \
  -c "COPY marts.mart_dashboard_harga_pangan TO '/opt/airflow/data/mart_dashboard.parquet' (FORMAT PARQUET);"

# Copy file dari container ke mesin lokal
docker cp pihps-airflow-scheduler:/opt/airflow/data/mart_modelling.csv ./output/
docker cp pihps-airflow-scheduler:/opt/airflow/data/mart_dashboard.parquet ./output/
```

### Opsi 3: Akses via Python (di luar container)

Copy file DuckDB ke lokal, lalu query dengan Python:

```bash
# Copy database ke mesin lokal
docker cp pihps-airflow-scheduler:/opt/airflow/data/pihps.duckdb ./pihps.duckdb
```

```python
import duckdb
import pandas as pd

# Buka koneksi (read-only agar aman)
conn = duckdb.connect("pihps.duckdb", read_only=True)

# Load ke pandas DataFrame
df_modelling = conn.execute("""
    SELECT * FROM marts.mart_modelling_harga_pangan
""").fetchdf()

df_dashboard = conn.execute("""
    SELECT * FROM marts.mart_dashboard_harga_pangan
    WHERE tanggal >= CURRENT_DATE - INTERVAL '30 days'
""").fetchdf()

print(f"Modelling: {df_modelling.shape}")
print(f"Dashboard: {df_dashboard.shape}")

conn.close()
```

> **Catatan:** Saat copy file DuckDB, pastikan tidak ada proses yang sedang menulis ke database (DuckDB menggunakan single-writer lock). Idealnya lakukan copy saat tidak ada DAG yang sedang berjalan.

### Opsi 4: Akses via Jupyter Notebook

```bash
# Install duckdb di environment lokal
pip install duckdb pandas jupyter

# Copy database
docker cp pihps-airflow-scheduler:/opt/airflow/data/pihps.duckdb ./pihps.duckdb

# Jalankan Jupyter
jupyter notebook
```

```python
# Di notebook cell
import duckdb

conn = duckdb.connect("pihps.duckdb", read_only=True)

# Langsung ke DataFrame
df = conn.sql("""
    SELECT
        tanggal,
        komoditas_nama,
        kota_nama,
        harga_aktual,
        rolling_avg_7d,
        harga_zscore_30d
    FROM marts.mart_modelling_harga_pangan
    WHERE komoditas_nama ILIKE '%cabai%'
    ORDER BY tanggal DESC
""").df()

df.head()
```

---

## Data Dictionary

### `marts.mart_modelling_harga_pangan`

Dataset untuk training model ML/forecasting. Grain: **1 row per (tanggal, comcat_id, kota_id)**.  
Hanya data dari **Pasar Tradisional**.

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| `tanggal` | DATE | Tanggal harga |
| `comcat_id` | VARCHAR | ID komoditas (dari PIHPS) |
| `komoditas_nama` | VARCHAR | Nama komoditas (contoh: "Beras Kualitas Super I") |
| `provinsi_id` | INTEGER | ID provinsi (12=Jabar, 13=DKI) |
| `provinsi_nama` | VARCHAR | Nama provinsi |
| `kota_id` | INTEGER | ID kota (PIHPS internal) |
| `kota_nama` | VARCHAR | Nama kota |
| `satuan` | VARCHAR | Satuan harga (kg, butir, liter) |
| **Target** | | |
| `harga_aktual` | DOUBLE | Harga hari ini (Rp) — **target variable untuk model** |
| **Lag Features** | | |
| `harga_lag_1d` | DOUBLE | Harga 1 hari lalu |
| `harga_lag_7d` | DOUBLE | Harga 7 hari lalu |
| `harga_lag_14d` | DOUBLE | Harga 14 hari lalu |
| `harga_lag_30d` | DOUBLE | Harga 30 hari lalu |
| `delta_harga_1d` | DOUBLE | Selisih harga vs kemarin (Rp) |
| `delta_harga_7d` | DOUBLE | Selisih harga vs 7 hari lalu (Rp) |
| `pct_change_1d` | DOUBLE | Perubahan % vs kemarin |
| `pct_change_7d` | DOUBLE | Perubahan % vs 7 hari lalu |
| **Rolling Stats** | | |
| `rolling_avg_7d` | DOUBLE | Rata-rata harga 7 hari terakhir |
| `rolling_std_7d` | DOUBLE | Standar deviasi harga 7 hari terakhir |
| `rolling_avg_30d` | DOUBLE | Rata-rata harga 30 hari terakhir |
| `rolling_std_30d` | DOUBLE | Standar deviasi harga 30 hari terakhir |
| `rolling_min_30d` | DOUBLE | Harga minimum 30 hari terakhir |
| `rolling_max_30d` | DOUBLE | Harga maksimum 30 hari terakhir |
| `avg_harga_nasional` | DOUBLE | Rata-rata harga semua kota pada hari yang sama |
| `harga_zscore_30d` | DOUBLE | Z-score harga (normalisasi terhadap rolling 30 hari) |
| `harga_ratio_nasional` | DOUBLE | Rasio harga lokal / rata-rata nasional |
| **Calendar Features** | | |
| `tahun` | INTEGER | Tahun |
| `bulan` | INTEGER | Bulan (1-12) |
| `kuartal` | INTEGER | Kuartal (1-4) |
| `hari_dalam_minggu` | INTEGER | Hari dalam minggu (0=Minggu, 6=Sabtu) |
| `is_weekday` | INTEGER | 1 = hari kerja, 0 = weekend |
| `is_ramadan_season` | INTEGER | 1 = bulan Maret-Mei (proxy musim Ramadan) |
| `is_year_end_season` | INTEGER | 1 = bulan Desember-Januari |

---

### `marts.mart_dashboard_harga_pangan`

Dataset untuk dashboard monitoring. Grain: **1 row per (tanggal, comcat_id, kota_id, pasar_tipe)**.  
Semua tipe pasar.

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| `tanggal` | DATE | Tanggal harga |
| `comcat_id` | VARCHAR | ID komoditas |
| `komoditas_nama` | VARCHAR | Nama komoditas |
| `satuan` | VARCHAR | Satuan harga |
| `provinsi_id` | INTEGER | ID provinsi |
| `provinsi_nama` | VARCHAR | Nama provinsi |
| `kota_id` | INTEGER | ID kota |
| `kota_nama` | VARCHAR | Nama kota |
| `pasar_tipe` | INTEGER | Tipe pasar (1-4) |
| `pasar_tipe_label` | VARCHAR | Label (Pasar Tradisional, Modern, dll) |
| **Harga** | | |
| `harga_hari_ini` | DOUBLE | Harga hari ini (Rp) |
| `harga_kemarin` | DOUBLE | Harga kemarin |
| `harga_minggu_lalu` | DOUBLE | Harga 7 hari lalu |
| `harga_bulan_lalu` | DOUBLE | Harga 30 hari lalu |
| **Delta** | | |
| `delta_1d` | DOUBLE | Selisih vs kemarin (Rp) |
| `delta_7d` | DOUBLE | Selisih vs minggu lalu (Rp) |
| `delta_30d` | DOUBLE | Selisih vs bulan lalu (Rp) |
| `pct_change_1d` | DOUBLE | Perubahan % vs kemarin |
| `pct_change_7d` | DOUBLE | Perubahan % vs minggu lalu |
| **Benchmark** | | |
| `harga_rata_nasional` | DOUBLE | Rata-rata harga nasional hari itu |
| `harga_min_nasional` | DOUBLE | Harga terendah nasional |
| `harga_maks_nasional` | DOUBLE | Harga tertinggi nasional |
| `jumlah_kota_dilaporkan` | INTEGER | Jumlah kota yang melapor |
| `rasio_vs_nasional` | DOUBLE | Rasio harga lokal / nasional (>1 = lebih mahal) |
| **Status** | | |
| `status_harga_harian` | VARCHAR | Naik / Turun / Stabil (vs kemarin) |
| `status_harga_mingguan` | VARCHAR | Naik / Turun / Stabil (vs minggu lalu) |
| `is_harga_tinggi_alert` | BOOLEAN | TRUE jika harga >10% di atas rata-rata nasional |

---

### `marts.mart_dashboard_ringkasan_nasional`

Ringkasan level nasional. Grain: **1 row per (tanggal, comcat_id, pasar_tipe)**.

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| `rata_harga_nasional` | DOUBLE | Rata-rata harga semua kota |
| `harga_min` | DOUBLE | Harga minimum |
| `harga_maks` | DOUBLE | Harga maksimum |
| `std_harga` | DOUBLE | Standar deviasi antar kota |
| `jumlah_kota` | INTEGER | Jumlah kota yang melapor |
| `jumlah_provinsi` | INTEGER | Jumlah provinsi |
| `jumlah_kota_alert` | INTEGER | Kota dengan harga tinggi (>10% avg) |
| `kota_harga_naik` | INTEGER | Jumlah kota harga naik |
| `kota_harga_turun` | INTEGER | Jumlah kota harga turun |
| `kota_harga_stabil` | INTEGER | Jumlah kota harga stabil |
| `delta_nasional_1d` | DOUBLE | Perubahan harga nasional vs kemarin |
| `pct_change_nasional_1d` | DOUBLE | Perubahan % nasional vs kemarin |
| `status_nasional` | VARCHAR | Naik / Turun / Stabil (mayoritas kota) |

---

## Konfigurasi

### Environment Variables (`.env`)

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `AIRFLOW_UID` | `50000` | UID untuk Airflow user di container |
| `AIRFLOW__CORE__FERNET_KEY` | *(generate)* | Encryption key Airflow |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | *(generate)* | Session secret key |
| `PIHPS_BASE_URL` | `https://www.bi.go.id/hargapangan/WebSite` | Base URL API PIHPS |
| `PIHPS_REQUEST_DELAY_SECONDS` | `2` | Delay antar request (rate limit) |
| `DUCKDB_PATH` | `/opt/airflow/data/pihps.duckdb` | Path file DuckDB di container |
| `DBT_TARGET` | `prod` | dbt target profile |

### Docker Services

| Service | Container Name | Port | Deskripsi |
|---------|---------------|------|-----------|
| `postgres` | `pihps-postgres` | 5432 (internal) | Metadata DB Airflow |
| `airflow-webserver` | `pihps-airflow-webserver` | **8080** | Airflow Web UI |
| `airflow-scheduler` | `pihps-airflow-scheduler` | 8974 (internal) | Scheduler + Worker |

### Docker Volumes

| Volume | Mount Point | Isi |
|--------|-------------|-----|
| `pihps-duckdb` | `/opt/airflow/data` | File database DuckDB |
| `postgres-db` | `/var/lib/postgresql/data` | Metadata Airflow |
| `airflow-logs` | `/opt/airflow/logs` | Log Airflow |

---

## Troubleshooting

### Pipeline tidak jalan / data tidak bertambah

```bash
# Cek status DAG
docker exec pihps-airflow-scheduler airflow dags list

# Cek log task terakhir
docker exec pihps-airflow-scheduler airflow tasks logs data_ready_modelling extract_harga_historis -1

# Cek checkpoint (kapan terakhir berhasil)
docker exec pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb \
  -c "SELECT * FROM raw.pipeline_log ORDER BY started_at DESC LIMIT 5;"
```

### Reset pipeline (tarik ulang dari awal)

```bash
# Hapus checkpoint agar extract mulai dari 2020
docker exec pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb \
  -c "DELETE FROM raw.pipeline_log;"

# Opsional: hapus semua data
docker exec pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb \
  -c "DELETE FROM raw.harga_pangan;"
```

### DuckDB locked

DuckDB menggunakan single-writer lock. Hanya satu proses yang bisa menulis pada satu waktu.

- Pastikan tidak ada DAG lain yang sedang berjalan saat akses data
- Gunakan `read_only=True` saat buka koneksi dari luar container
- Jika mau query bersamaan dengan DAG, copy file database terlebih dahulu

### Container tidak healthy

```bash
# Lihat status semua container
docker compose ps

# Lihat log error
docker compose logs airflow-scheduler --tail=50
docker compose logs airflow-webserver --tail=50

# Restart semua service
docker compose restart
```

### Data setelah `docker compose down` hilang

Data DuckDB disimpan di Docker named volume (`pihps-duckdb`). Data **tetap ada** selama volume tidak dihapus. Yang menghapus volume:

```bash
# INI menghapus volume (data hilang!)
docker compose down -v

# INI aman (data tetap ada)
docker compose down
docker compose up -d
```

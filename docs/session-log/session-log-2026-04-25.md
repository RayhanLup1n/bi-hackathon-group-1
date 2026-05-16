# Session Log — ETL Pipeline Development

**Tanggal:** 25 April 2026  
**Branch:** `feat/etl-automation`  
**Dikerjakan oleh:** Rayhan + Claude AI

---

## Ringkasan

Session ini fokus pada pembangunan **data pipeline end-to-end** untuk mengekstrak data harga pangan dari portal BI PIHPS (Bank Indonesia - Pusat Informasi Harga Pangan Strategis), mentransformasinya melalui dbt, dan menyimpan hasilnya di DuckDB sebagai analytical database.

Pipeline ini terdiri dari 2 DAG Airflow:
1. **`data_ready_modelling`** — Ekstraksi historis untuk dataset ML/forecasting
2. **`data_ready_dashboard`** — Ekstraksi harian (D-1) untuk monitoring dashboard

---

## Apa yang Dikerjakan

### 1. Setup Infrastruktur Docker

- Membuat `Dockerfile` berbasis `apache/airflow:2.9.2-python3.11`
- Membuat `docker-compose.yml` dengan 3 service (PostgreSQL, Airflow Webserver, Airflow Scheduler)
- Setup Docker volumes untuk DuckDB, Airflow logs, dan PostgreSQL metadata
- Konfigurasi environment variables via `.env` dan Pydantic Settings

### 2. Extractor — Koneksi ke API PIHPS

- Membuat `PihpsExtractor` yang menangani:
  - Autentikasi via XSRF Token + Session Cookie (ASP.NET Core antiforgery)
  - Parsing response format **pivot table** dari API (tanggal sebagai JSON keys, bukan flat rows)
  - Reverse mapping nama komoditas → comcat_id (karena API hanya mengembalikan nama)
  - Rate limiting (2 detik per request) untuk menghindari throttling
- Membuat `extract_harga_per_wilayah` untuk iterasi per provinsi → per kota
- Membuat Pydantic model (`HargaKomoditasRecord`) untuk validasi data

### 3. Loader — DuckDB Upsert

- Membuat `DuckDBLoader` dengan:
  - Schema initialization (raw, staging, marts)
  - Tabel: `harga_pangan`, `dim_provinsi`, `dim_kota`, `pipeline_log`
  - Upsert logic via `INSERT WHERE NOT EXISTS` pada natural key `(tanggal, comcat_id, kota_id, pasar_nama)`
  - Audit columns: `_extracted_at`, `_source`

### 4. Transformasi dbt

- **Staging** (`stg_harga_pangan` — VIEW):
  - Type casting, text cleaning, price validation
  - Label mapping (pasar_tipe → nama)
  - Time dimension extraction (tahun, bulan, kuartal, hari)
  - Deduplikasi via ROW_NUMBER()

- **Mart Modelling** (`mart_modelling_harga_pangan` — TABLE):
  - Lag features: harga_lag_1d, 7d, 14d, 30d
  - Delta & pct_change features
  - Rolling statistics: avg, std, min, max (window 7d & 30d)
  - Calendar features: is_weekday, is_ramadan_season, is_year_end_season
  - Normalisasi: harga_zscore_30d, harga_ratio_nasional

- **Mart Dashboard** (`mart_dashboard_harga_pangan` — TABLE):
  - Harga perbandingan: hari ini, kemarin, minggu lalu, bulan lalu
  - Status harga: Naik/Turun/Stabil
  - Benchmark nasional & alert (>10% di atas rata-rata)

- **Mart Ringkasan Nasional** (`mart_dashboard_ringkasan_nasional` — TABLE):
  - Agregasi harga nasional per komoditas
  - Distribusi status kota (naik/turun/stabil)
  - Status nasional berdasarkan mayoritas

### 5. DAG Airflow

- **DAG 1 (`data_ready_modelling`):**
  - 7 tasks sequential: init → master data → extract historis → staging → mart → test → log
  - Mendukung incremental via checkpoint di `pipeline_log`
  - Target: 10 kota di Jawa Barat & DKI Jakarta

- **DAG 2 (`data_ready_dashboard`):**
  - 7 tasks sequential: init → health check → extract D-1 → staging → mart → test → log
  - Schedule: daily 00:00 UTC (07:00 WIB)
  - Termasuk source availability check (fail-fast)

### 6. Debugging & Fixing

Beberapa masalah yang ditemukan dan diperbaiki selama session:

| Masalah | Penyebab | Fix |
|---------|----------|-----|
| Data "sudah up-to-date" padahal belum extract | Stale entry di `pipeline_log` dari test sebelumnya | `DELETE FROM raw.pipeline_log` |
| 0 records diextract | Parser mengasumsikan flat response, padahal API mengembalikan pivot table | Rewrite `_parse_grid_response` untuk unpivot date columns |
| Harga "15,150" diparsing jadi 15.15 | Koma dianggap decimal separator (format Indonesia) | Ubah `parse_harga` — koma sebagai thousands separator |
| `changes()` function not found | DuckDB tidak punya `changes()` seperti SQLite | Ganti dengan count before/after pattern |
| Data NULL untuk provinsi/kota | Ekstraksi tanpa filter provinsi = data rata-rata nasional | Buat `extract_harga_per_wilayah` yang iterasi per kota |
| PowerShell quoting error | Single quotes di SQL dikonsumsi PowerShell | Simplifikasi command tanpa WHERE clause |

### 7. Restrukturisasi Project

- Memindahkan semua file pipeline ke subfolder `etl/` agar bersih untuk kolaborasi tim
- Root hanya berisi `README.md` dan `.gitignore`
- Tidak perlu perubahan konten file (path sudah relative/container-internal)

### 8. Dokumentasi

- Membuat `etl/README.md` lengkap:
  - Arsitektur, struktur folder, quick start
  - Penjelasan detail kedua pipeline
  - **4 cara akses data** (Docker CLI, export CSV/Parquet, Python, Jupyter)
  - Data dictionary lengkap untuk semua mart table
  - Konfigurasi dan troubleshooting
- Update root `README.md` sebagai entry point project

---

## Hasil Akhir

### Data yang Berhasil Diekstrak

| Metrik | Nilai |
|--------|-------|
| Total records di `raw.harga_pangan` | **346,080** |
| Provinsi | 2 (Jawa Barat, DKI Jakarta) |
| Kota | 10 |
| Komoditas | 21 |
| Rentang tanggal | 2020-01-01 — 2026-04-25 |
| Tipe pasar | Pasar Tradisional |

### Status Pipeline

| DAG | Status | Catatan |
|-----|--------|---------|
| `data_ready_modelling` | Berhasil (via UI) | Full historical load selesai |
| `data_ready_dashboard` | Berhasil (via UI) | Tested manual trigger |

### Tabel di DuckDB

| Schema | Tabel | Jumlah Rows (approx) |
|--------|-------|---------------------|
| `raw` | `harga_pangan` | 346,080 |
| `raw` | `dim_provinsi` | 2 |
| `raw` | `dim_kota` | 10 |
| `raw` | `pipeline_log` | N (per run) |
| `staging` | `stg_harga_pangan` (VIEW) | 346,080 |
| `marts` | `mart_modelling_harga_pangan` | ~346,000 |
| `marts` | `mart_dashboard_harga_pangan` | ~346,000 |
| `marts` | `mart_dashboard_ringkasan_nasional` | ~34,000 |

---

## Belum Dikerjakan / Next Steps

- [ ] Integrasi dashboard (BI tool) dengan `mart_dashboard_harga_pangan` — data sudah siap, belum diconnect ke dashboard tool
- [ ] Training model ML deteksi inflasi menggunakan `mart_modelling_harga_pangan`
- [ ] Evaluasi apakah proxy `is_ramadan_season` (bulan 3-5) perlu diganti dengan kalender hijriah yang akurat
- [ ] Monitoring & alerting jika DAG gagal (email/Slack notification)
- [ ] Unit tests untuk extractor dan loader

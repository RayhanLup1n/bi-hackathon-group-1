# R.A.D.A.R Pangan — Project Overview

## TLDR

R.A.D.A.R Pangan (*Real-time Anti-inflation Detection, Analysis & Response*) adalah platform web untuk membantu pemantauan dan pengendalian volatilitas harga pangan di Indonesia. Platform ini menggabungkan data harga pangan, kalender hari besar, data cuaca, batas Harga Eceran Tertinggi (HET), analisis penyebab kenaikan harga, serta prediksi machine learning.

Project ini dikembangkan oleh Tim Simatana untuk Hackathon PIDI/Digdaya 2026 dengan tema Digitalisasi Ketahanan Pangan. Target pengguna utamanya adalah instansi dan analis yang terlibat dalam pengendalian inflasi pangan, seperti TPID, Bapanas, Bulog, dan ID Food.

## 1. Identitas Project

| Item | Detail |
|---|---|
| Nama | R.A.D.A.R Pangan |
| Kepanjangan | Real-time Anti-inflation Detection, Analysis & Response |
| Versi aplikasi | 0.7.0 |
| Jenis aplikasi | Web application dan data/ML platform |
| Domain | Pemantauan harga pangan dan pengendalian inflasi |
| Target pengguna | TPID, Bapanas, Bulog, ID Food, dan analis terkait |
| Backend | FastAPI |
| Frontend | HTML, Alpine.js, Chart.js, dan CSS |
| Data warehouse | Google BigQuery |
| Serving database | PostgreSQL, dengan Supabase pada development/demo |
| ETL/orchestration | Kestra, extractor Python, dan dbt-bigquery |
| Machine learning | LightGBM, Bayesian/change-point detection, dan LLM reasoning agent |
| Deployment | Docker Compose dan Railway |

## 2. Latar Belakang Masalah

Harga komoditas pangan dapat meningkat karena kombinasi beberapa faktor, antara lain:

- kenaikan permintaan pada hari besar atau musim tertentu;
- cuaca ekstrem yang mengganggu produksi dan distribusi;
- kenaikan harga yang terjadi secara serentak di banyak kota;
- keterbatasan stok dan gangguan distribusi;
- harga aktual yang mendekati atau melampaui HET.

Tanpa sistem terintegrasi, pemantauan harga, pencarian penyebab, dan penentuan respons dapat berjalan terpisah. R.A.D.A.R Pangan dirancang untuk menyatukan proses tersebut dalam satu alur: mengumpulkan data, menyajikan kondisi harga, mendeteksi risiko, menganalisis penyebab, lalu memberikan konteks untuk menentukan intervensi.

## 3. Tujuan dan Nilai Utama

Platform ini memiliki empat tujuan utama:

1. Memberikan visibilitas terhadap kondisi harga pangan harian.
2. Mendeteksi komoditas dan wilayah yang berpotensi mengalami tekanan harga.
3. Membantu analis memahami kemungkinan root cause secara sistematis.
4. Menyediakan prediksi dan rekomendasi respons agar intervensi dapat dilakukan lebih awal.

Nilai pembeda project ini adalah penggabungan monitoring, analisis penyebab, prediksi, dan respons dalam satu platform. Dashboard tidak hanya menampilkan angka harga, tetapi juga menghubungkan harga dengan HET, cuaca, kalender, persebaran regional, dan hasil analisis.

## 4. Cakupan MVP

### 4.1 Komoditas

MVP berfokus pada enam komoditas berikut:

| Komoditas | ID |
|---|---|
| Bawang Merah Ukuran Sedang | `com_11` |
| Bawang Putih Ukuran Sedang | `com_12` |
| Cabai Merah Besar | `com_13` |
| Cabai Merah Keriting | `com_14` |
| Cabai Rawit Hijau | `com_15` |
| Cabai Rawit Merah | `com_16` |

### 4.2 Wilayah

Scope MVP mencakup empat provinsi dan 18 kota/kabupaten:

- Banten;
- Jawa Barat;
- DKI Jakarta;
- Sulawesi Selatan.

Wilayah yang disebutkan dalam proposal mencakup Serang, Cilegon, Tangerang, Bandung, Cirebon, Tasikmalaya, Bekasi, Bogor, Depok, Sukabumi, Jakarta Pusat, Makassar, Palopo, Parepare, Watampone, dan Bulukumba, beserta beberapa wilayah kabupaten terkait.

### 4.3 Di luar cakupan MVP

Project tidak ditujukan untuk:

- aplikasi konsumen atau marketplace;
- komoditas di luar enam komoditas MVP;
- cakupan nasional penuh di luar wilayah yang ditentukan;
- social media sentiment analysis;
- pelacakan fisik supply chain atau IoT;
- pembayaran dan e-commerce;
- aplikasi mobile native;
- query BigQuery secara langsung untuk setiap request user pada serving runtime.

## 5. Fitur Utama

### 5.1 Dashboard Monitoring

Dashboard menampilkan kondisi harga komoditas dan indikator risiko secara ringkas. Komponen utamanya mencakup status HET, informasi prediksi ML, dan snapshot analisis Bowtie. Dashboard dirancang tetap dapat digunakan ketika ML server tidak tersedia melalui mekanisme graceful degradation.

### 5.2 HET Monitor

HET Monitor membandingkan harga aktual terhadap nilai HET dan mengelompokkan status menjadi beberapa level, seperti:

- `AMAN`;
- `WASPADA`;
- `KRITIS`;
- `MELAMPAUI`.

Status tersebut membantu analis memprioritaskan komoditas yang perlu diperiksa lebih lanjut.

### 5.3 RCA/FTA dan Bowtie Analysis

Analisis rule-based menggunakan pemeriksaan berurutan untuk mengidentifikasi kemungkinan penyebab kenaikan harga. Pemeriksaan RCA mencakup:

1. kalender hari raya dalam window H-14 sampai H+3;
2. cuaca ekstrem, seperti curah hujan tinggi, drought, suhu tinggi, atau angin kencang;
3. persebaran kenaikan harga antar kota;
4. indikasi stok pedagang.

Engine menggunakan early exit: ketika kondisi penyebab terpenuhi, diagnosis dapat langsung dihasilkan tanpa melanjutkan pemeriksaan berikutnya.

Bowtie Analysis melengkapi RCA dengan:

- enam threat pada Fault Tree Analysis;
- barrier pencegahan;
- barrier mitigasi;
- severity level dari L0 sampai L4.

Threat yang dimodelkan mencakup hari raya, spekulasi, cuaca, stok, distribusi, dan impor. Barrier mitigasi dapat berupa operasi pasar, subsidi, atau distribusi darurat.

### 5.4 Prediksi ML

Service ML terpisah menyediakan prediksi harga dan deteksi risiko dalam tiga lapisan:

1. **Forecasting** — LightGBM quantile regression untuk prediksi P50 dan P90 dengan horizon 7 dan 14 hari.
2. **Detection** — analisis HET breach, change point, z-score, dan regional disparity.
3. **Decision** — LLM reasoning agent untuk menyusun konteks serta rekomendasi intervensi berdasarkan data dan tools analitik.

Model dapat dijalankan sebagai service terpisah pada port `8001`. Backend utama mem-proxy request melalui endpoint `/api/ml/*`.

### 5.5 Data Cuaca

Data cuaca diambil dari Open-Meteo dan digunakan sebagai salah satu sinyal dalam RCA serta fitur prediksi. Data ini membantu menghubungkan anomali harga dengan kondisi cuaca pada wilayah terkait.

### 5.6 Authentication dan RBAC

Platform menerapkan JWT authentication dan role-based access control. Role utama yang tersedia adalah:

| Role | Akses umum |
|---|---|
| Viewer | Dashboard monitoring |
| Analyst | Dashboard, analisis RCA/Bowtie, dan prediksi |
| Admin | Seluruh akses serta manajemen user/data quality |

Password user disimpan menggunakan bcrypt. Backend menggunakan guard berbasis dependency FastAPI untuk membatasi endpoint berdasarkan role.

## 6. Halaman Aplikasi

| Halaman | URL | Fungsi | Akses minimum |
|---|---|---|---|
| Login | `/login` | Authentication user | Semua |
| Dashboard | `/` | Monitoring harga dan status risiko | Viewer |
| Panduan Analis | `/guide` | Panduan penggunaan platform | Semua |
| Analisis | `/analysis` | RCA/FTA dan Bowtie analysis | Analyst |
| Prediksi | `/prediksi` | Prediksi dan hasil analisis ML | Analyst |
| Admin | `/admin` | Administrasi user dan data quality | Admin |

Frontend menggunakan file HTML statis yang disajikan oleh FastAPI. Alpine.js digunakan untuk interaksi halaman dan Chart.js tersedia untuk visualisasi data prediksi.

## 7. Arsitektur Sistem

### 7.1 Gambaran umum

```text
BI PIHPS ───────────────┐
Kalender hari besar ────┼──> ETL / Kestra + dbt ──> BigQuery Bronze/Silver
Open-Meteo ─────────────┘                                  │
                                                           │ sync / transform
                                                           v
                                                  PostgreSQL Gold/Serving
                                                           │
                                      ┌────────────────────┴──────────────────┐
                                      v                                       v
                              FastAPI App :8000                       ML Server :8001
                                      │                                       │
                                      └────────── Frontend HTML ──────────────┘
```

### 7.2 Medallion data architecture

- **Bronze** menyimpan data mentah atau hasil ekstraksi awal.
- **Silver** berisi data yang sudah distandardisasi dan ditransformasi melalui dbt.
- **Gold/Serving** berisi mart atau tabel yang dioptimalkan untuk kebutuhan aplikasi, API, dan ML.

BigQuery digunakan untuk proses batch dan data warehouse. PostgreSQL/Supabase digunakan sebagai serving layer untuk kebutuhan aplikasi dengan latency yang lebih rendah.

### 7.3 FastAPI application

`main.py` adalah entry point aplikasi. Saat startup, aplikasi melakukan beberapa hal berikut:

1. Memuat environment variables dari `.envs/.env`.
2. Menyiapkan kredensial GCP dari file atau `GOOGLE_CREDENTIALS_BASE64` jika tersedia.
3. Menginisialisasi connection pool PostgreSQL.
4. Memuat mapping komoditas.
5. Melakukan inisialisasi/seed user authentication.
6. Menyediakan API, static assets, dan halaman HTML.

Aplikasi juga memiliki health endpoint `/health`, security headers, CORS configuration, serta optional Swagger/OpenAPI melalui `ENABLE_DOCS` atau mode debug.

### 7.4 ETL dan transformasi

Folder `etl/` berisi extractor data, konfigurasi, script operasional, flow Kestra, serta project dbt. Sumber utama yang terlihat di repository meliputi:

- BI PIHPS untuk harga pangan;
- Open-Meteo untuk cuaca;
- `python-holidays` untuk kalender hari besar;
- data referensi seperti HET dan musim panen.

Flow Kestra tersedia untuk full pipeline dan daily pipeline. Model dbt berada di `etl/dbt_project/models/` dan terbagi menjadi staging, marts, dashboard, serta modelling.

### 7.5 ML service

Folder `ml/` merupakan service terpisah yang memiliki pipeline feature engineering, training, detection, decision, model artifacts, dan API inference. Model yang tersedia mencakup kombinasi quantile dan horizon:

- `q50`, horizon 7 hari;
- `q90`, horizon 7 hari;
- `q50`, horizon 14 hari;
- `q90`, horizon 14 hari.

Model inference menggunakan kontrak endpoint pada port `8001`, sementara aplikasi utama mengaksesnya melalui proxy.

## 8. Struktur Repository

```text
bi-hackathon-group-1/
├── config/              # Application settings dan threshold
├── frontend/            # HTML pages, CSS, logo, dan asset
├── src/
│   ├── api/             # FastAPI routes, auth, dan ML proxy
│   ├── data/            # Database client dan data access layer
│   ├── engine/          # HET, RCA, dan Bowtie business logic
│   └── models/          # Pydantic schemas
├── etl/
│   ├── extractors/      # PIHPS, Open-Meteo, dan HTTP client
│   ├── scripts/         # Load, sync, seed, dan migration scripts
│   ├── kestra/          # Dockerfile dan flow orchestration
│   └── dbt_project/     # Staging dan mart transformations
├── ml/                  # Training pipeline dan inference service
├── infra/               # Terraform untuk infrastructure GCP/BigQuery
├── tests/               # Unit, schema, dan end-to-end tests
├── docs/                # PRD, FRD, ERD, SDA, deployment, dan demo docs
├── main.py              # FastAPI application entry point
├── pyproject.toml       # Project metadata dan dependency uv
├── Dockerfile           # Image aplikasi utama
├── docker-compose.yml   # App, ML, dan Kestra services
├── railway.toml         # Deployment configuration aplikasi
└── Procfile             # Start command deployment
```

## 9. API Utama

API dikelompokkan berdasarkan domain berikut:

| Prefix/Endpoint | Fungsi |
|---|---|
| `/api/commodities` | Daftar komoditas tersedia |
| `/api/commodity/{key}` | Data satu komoditas |
| `/api/prices/...` | Ringkasan dan histori harga |
| `/api/analysis` | RCA/FTA analysis |
| `/api/bowtie` | Bowtie analysis |
| `/api/het` | Status HET |
| `/api/cuaca` | Data dan ringkasan cuaca |
| `/api/stok` | Endpoint terkait stok |
| `/api/predictions` | Data prediksi yang tersimpan |
| `/api/ml/*` | Proxy ke ML inference server |
| `/api/auth/*` | Login, session, dan user management |
| `/api/data-quality` | Pemeriksaan kualitas data, terutama admin-only |
| `/health` | Liveness check aplikasi |

Detail route dan schema dapat dilihat di `src/api/`, `src/models/schemas.py`, serta Swagger ketika API docs diaktifkan.

## 10. Data dan Database

Data utama project mencakup:

- harga pangan harian;
- cuaca harian;
- kalender hari besar;
- kalender musim panen;
- referensi HET;
- hasil prediksi ML;
- data inflasi dan referensi historis;
- user dan role aplikasi.

Tabel atau mart yang disebutkan dalam dokumentasi project antara lain `app.harga_pangan`, `app.cuaca_harian`, `app.ml_predictions`, `app.hari_besar`, `app.musim_panen`, `app.het_reference`, `app.users`, serta dashboard/modelling marts.

Source of truth dan lokasi runtime perlu diperhatikan: dokumentasi lama di repository masih memuat beberapa fase migrasi BigQuery ke PostgreSQL. Implementasi utama saat ini menginisialisasi PostgreSQL/Supabase sebagai Gold/serving layer, sedangkan BigQuery tetap digunakan untuk kebutuhan warehouse, ETL, dan data-quality tertentu.

## 11. Setup dan Cara Menjalankan

### 11.1 Prasyarat

- Python sesuai konfigurasi project, minimal `>=3.10` pada `pyproject.toml`.
- `uv` sebagai package manager yang direkomendasikan.
- Docker dan Docker Compose jika menjalankan seluruh service.
- Google Cloud CLI dan Application Default Credentials jika membutuhkan BigQuery.
- Credential PostgreSQL/Supabase sesuai environment.

### 11.2 Local development

```bash
uv sync
uv run uvicorn main:app --reload
```

Aplikasi tersedia di `http://localhost:8000`. Endpoint dokumentasi tersedia di `/docs` apabila debug atau `ENABLE_DOCS=true` diaktifkan.

Environment variables utama meliputi:

- `SUPABASE_HOST`, `SUPABASE_PORT`, `SUPABASE_DB`, `SUPABASE_USER`, `SUPABASE_PASSWORD`;
- `GCP_PROJECT`, `BQ_LOCATION`;
- `JWT_SECRET`;
- `GOOGLE_APPLICATION_CREDENTIALS` atau `GOOGLE_CREDENTIALS_BASE64`;
- `ML_SERVER_URL`;
- `CORS_ORIGINS` dan `ENABLE_DOCS`.

Jangan memasukkan credential asli ke repository. Gunakan file environment lokal yang tidak di-commit.

### 11.3 Docker Compose

```bash
# Aplikasi utama
docker compose up app

# Aplikasi + ML
docker compose --profile ml up

# Aplikasi + ETL/Kestra
docker compose --profile etl up

# Semua service
docker compose --profile ml --profile etl up
```

Service utama:

| Service | Port | Keterangan |
|---|---:|---|
| `app` | 8000 | FastAPI + frontend |
| `ml-model` | 8001 | ML inference, profile `ml` |
| `kestra` | 8080 | ETL orchestration UI, profile `etl` |
| `kestra-postgres` | internal | Metadata store Kestra |

### 11.4 dbt

```bash
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project
uv run dbt test --profiles-dir etl/dbt_project --project-dir etl/dbt_project
```

Perintah ini memerlukan konfigurasi BigQuery dan credential yang valid.

## 12. Testing dan Quality Checks

Test suite berada di folder `tests/` dan mencakup:

- `test_weather_data.py` untuk data cuaca;
- `test_schemas.py` untuk validasi schema;
- `test_rca_engine.py` untuk rule dan diagnosis RCA;
- `test_het_monitor.py` untuk klasifikasi HET;
- `test_bowtie_engine.py` untuk analisis Bowtie;
- folder `tests/e2e/` untuk login, RBAC, navigation, dashboard, struktur HTML, responsive behavior, dan halaman RCA.

Perintah utama:

```bash
uv run pytest tests/ -v
```

Linting menggunakan Ruff dan konfigurasi berada di `pyproject.toml`.

Catatan: angka jumlah test dan status pada README dapat berubah. Untuk status terkini, jalankan test suite secara langsung di environment project.

## 13. Deployment

Project mendukung beberapa mode deployment:

- local development melalui Uvicorn;
- Docker Compose untuk environment terkontainerisasi;
- Railway untuk demo/cloud deployment;
- Terraform pada `infra/` untuk provisioning resource GCP/BigQuery.

Konfigurasi deployment aplikasi utama tersedia di `railway.toml`, `render.yaml`, `Procfile`, dan `Dockerfile`. Service ML memiliki konfigurasi deployment terpisah di `ml/railway.toml` dan `ml/Dockerfile`.

Pada cloud environment yang tidak dapat memasang file credential secara langsung, aplikasi mendukung `GOOGLE_CREDENTIALS_BASE64`. Nilai tersebut didecode saat startup dan ditulis ke temporary file selama process berjalan.

## 14. Graceful Degradation dan Dependency Runtime

ML dirancang sebagai service plug-and-play. Aplikasi utama masih dapat menjalankan fungsi monitoring dan analisis rule-based ketika ML server offline, meskipun fitur prediksi dan endpoint yang bergantung pada ML tidak tersedia.

Secara konseptual, runtime memiliki dua jalur:

```text
Harga + HET + cuaca + kalender
              │
              ├──> FastAPI + HET/RCA/Bowtie engine ──> Dashboard/Analysis
              │
              └──> ML server ──> Forecast/Detection/Decision ──> Prediksi/Alert
```

Pemisahan ini membantu development dan demo karena core application tidak sepenuhnya bergantung pada proses inference ML.

## 15. Status Project dan Catatan Penting

Project berada pada tahap prototype/demo-ready berdasarkan README dan dokumen project. Komponen utama yang sudah tersedia di repository meliputi:

- FastAPI application dan static frontend;
- authentication dan role-based access;
- HET monitor;
- RCA/FTA dan Bowtie engine;
- extractor dan ETL scripts;
- Kestra flows;
- dbt staging/mart models;
- ML training dan inference service;
- Docker Compose;
- Terraform infrastructure files;
- unit dan end-to-end tests;
- PRD, FRD, ERD, SDA, tech-stack, deployment, wireframe, dan demo documentation.

Beberapa dokumen seperti `docs/PROJECT_BREAKDOWN.md` dan proposal merekam keputusan atau backlog pada fase sebelumnya. Karena repository terus berkembang, dokumen tersebut perlu dibaca bersama source code terbaru sebelum dijadikan acuan implementasi. Khususnya, status data access BigQuery versus PostgreSQL/Supabase dapat berbeda antara dokumen historis dan implementasi terbaru.

## 16. Dokumentasi Existing

| Dokumen | Lokasi | Fokus |
|---|---|---|
| README utama | `README.md` | Setup, fitur, dan ringkasan arsitektur |
| PRD | `docs/prd/PRD.md` | Product requirements |
| FRD | `docs/frd/FRD.md` | Functional requirements |
| ERD | `docs/erd/ERD.md` | Entity relationship dan data flow |
| System Design | `docs/sda/SYSTEM_DESIGN.md` | Arsitektur dan system design |
| Tech Stack | `docs/tech-stack/TECH_STACK.md` | Teknologi yang digunakan |
| Deployment | `docs/DEPLOYMENT.md` | Deployment dan operational setup |
| Demo scenarios | `docs/demo-scenarios.md` | Skenario penggunaan/demo |
| ML README | `ml/README.md` | Training, inference, dan kontrak ML API |
| Project breakdown | `docs/PROJECT_BREAKDOWN.md` | Status dan backlog pada fase tertentu |

## 17. Ringkasan Alur Pengguna

1. User membuka halaman login dan melakukan authentication.
2. Backend menerbitkan atau memvalidasi JWT berdasarkan user dan role.
3. Viewer melihat dashboard harga, status HET, dan ringkasan risiko.
4. Analyst memilih komoditas atau wilayah untuk melihat histori, RCA/Bowtie, dan prediksi.
5. Backend mengambil data dari serving database dan menjalankan engine rule-based.
6. Jika tersedia, backend meneruskan request prediksi ke ML server.
7. Admin mengelola user atau menjalankan pemeriksaan data quality.
8. Hasil analisis digunakan sebagai konteks untuk koordinasi dan keputusan intervensi pangan.

## 18. Kesimpulan

R.A.D.A.R Pangan merupakan platform intelligence untuk harga pangan yang menggabungkan data engineering, web application, rule-based analysis, machine learning, dan deployment infrastructure. Repository ini sudah mencakup sebagian besar building block untuk sebuah prototype end-to-end: mulai dari ekstraksi data dan transformasi, penyimpanan warehouse/serving, API dan frontend, sampai prediksi serta analisis respons.

Fokus utama platform bukan sekadar menampilkan harga, melainkan mempercepat perpindahan dari **monitoring** ke **deteksi**, **analisis penyebab**, dan **rekomendasi respons**.


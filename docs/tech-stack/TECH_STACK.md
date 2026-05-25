# Tech Stack — R.A.D.A.R Pangan

> Tanggal: 25 Mei 2026 | Tim Simatana
> Referensi: [PRD](../prd/PRD.md) | [SDA](../sda/SYSTEM_DESIGN.md) | [ERD](../erd/ERD.md)

---

## 1. Stack Overview

```
┌────────────────────────────────────────────────────────┐
│                     FRONTEND                            │
│  HTML · Alpine.js 3.x · Chart.js 4.4.4 · Neobrutalism │
├────────────────────────────────────────────────────────┤
│                     BACKEND                             │
│  Python 3.10+ · FastAPI 0.115 · Pydantic 2.8           │
│  JWT (python-jose) · bcrypt · psycopg2                 │
├──────────────────────┬─────────────────────────────────┤
│   DATA WAREHOUSE     │      APP DATABASE               │
│   Google BigQuery    │      PostgreSQL 16               │
│   (Bronze + Silver)  │      (Gold / Serving)            │
├──────────────────────┴─────────────────────────────────┤
│                     PIPELINE                            │
│  Kestra 1.3.19 · dbt-bigquery 1.8 · Python extractors │
├────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE                      │
│  Docker · Terraform 1.9 · uv (package manager)        │
├────────────────────────────────────────────────────────┤
│                     ML (Teammate)                       │
│  LightGBM · Conformal Prediction · pandas              │
└────────────────────────────────────────────────────────┘
```

---

## 2. Frontend

| Technology | Version | Fungsi | Justifikasi |
|-----------|---------|--------|-------------|
| **HTML5** | — | Page structure | No build step, langsung serve, cepat develop |
| **Alpine.js** | 3.x (CDN) | Reactive UI, data binding | Ringan (~15KB), deklaratif, tidak perlu build toolchain |
| **Chart.js** | 4.4.4 (CDN) | Grafik harga + prediksi | Populer, responsive, canvas-based, gratis |
| **CSS Custom** | — | Neobrutalism design system | Full control, no framework overhead, distinctive untuk hackathon |
| **Google Fonts** | — | Inter + JetBrains Mono | Profesional, readable, gratis |

### Alternatif yang Dipertimbangkan

| Alternatif | Alasan Tidak Dipilih |
|-----------|---------------------|
| React.js (PWA) | Ada di Proposal 1, tapi timeline < 3 minggu tidak cukup untuk setup build toolchain + migrasi |
| Vue.js | Lebih berat dari Alpine.js, perlu build step untuk production |
| Tailwind CSS | Butuh build step (PostCSS), bisa pakai CDN tapi bloated |
| Bootstrap | Tampilan generik, tidak memorable untuk hackathon demo |

### CSS Architecture Decision

| Aspect | Keputusan |
|--------|-----------|
| **File** | External CSS (`frontend/css/style.css`), bukan inline `<style>` |
| **Methodology** | CSS Custom Properties (`:root` variables) untuk design tokens |
| **Responsive** | Mobile-first, breakpoints di 768px dan 1024px |
| **Build** | Tidak ada — plain CSS, langsung serve oleh Nginx/FastAPI |

---

## 3. Backend

| Technology | Version | Fungsi | Justifikasi |
|-----------|---------|--------|-------------|
| **Python** | 3.10+ | Runtime | Ecosystem data/ML terlengkap (pandas, scikit-learn, dbt), satu bahasa untuk backend + pipeline + ML |
| **FastAPI** | 0.115.0 | Web framework | Async, auto-docs (Swagger), Pydantic validation, performa tinggi |
| **Pydantic** | ≥ 2.8.0 | Data validation | Native di FastAPI, type-safe, auto-serialize |
| **Uvicorn** | 0.30.6 | ASGI server | Standard untuk FastAPI, production-ready dengan Gunicorn |
| **python-jose** | 3.3.0 | JWT token | HS256 signing, decode, verify |
| **bcrypt** | ≥ 4.0.0 | Password hashing | Industry standard, timing-safe |
| **psycopg2-binary** | ≥ 2.9.9 | PostgreSQL driver | Paling mature Python PG driver, connection pooling |
| **google-cloud-bigquery** | ≥ 3.41.0 | BigQuery client | Official Google SDK, thread-safe |
| **httpx** | ≥ 0.27.0 | HTTP client | Async support, modern API (pengganti requests) |
| **python-multipart** | 0.0.9 | Form parsing | Required untuk OAuth2PasswordRequestForm di FastAPI |

### Alternatif yang Dipertimbangkan

| Alternatif | Alasan Tidak Dipilih |
|-----------|---------------------|
| Django + DRF | Terlalu berat untuk API-only app, convention-heavy |
| Flask | Kurang fitur bawaan (validasi, auto-docs), lebih banyak boilerplate |
| Node.js (Express) | Membutuhkan bahasa terpisah dari pipeline/ML (Python), menambah kompleksitas stack |
| SQLAlchemy ORM | Over-engineering untuk query sederhana, raw SQL lebih transparent |

---

## 4. Database

### 4.1 Google BigQuery (Data Warehouse)

| Aspect | Detail |
|--------|--------|
| **Layer** | Bronze (raw.*) + Silver (staging.*) |
| **Project** | `radar-pangan-hackathon` |
| **Region** | `asia-southeast2` (Jakarta) |
| **Auth** | Application Default Credentials (ADC) via `gcloud auth application-default login` |
| **Cost** | Free tier: 10 GB storage + 1 TB queries/bulan |
| **Partitioning** | `raw.harga_pangan` → DAY on `tanggal` (`require_partition_filter = true`) |
| **Clustering** | `comcat_id`, `provinsi_id`, `kota_id` |

**Justifikasi**: Optimal untuk analytical queries (aggregation, window functions) pada volume data besar (619K+ rows). Free tier cukup untuk 3+ tahun data.

### 4.2 PostgreSQL (Gold / Serving Layer)

| Aspect | Dev/Demo | Production |
|--------|----------|------------|
| **Provider** | Supabase (managed) | Docker `postgres:16-alpine` |
| **Layer** | Gold (marts.* + app.*) | Gold (marts.* + app.*) |
| **Cost** | Free (500 MB limit) | Included di VPS cost |
| **Latency** | ~50-200ms (cloud) | ~1-5ms (local Docker) |
| **Driver** | psycopg2 (pure PostgreSQL, no Supabase SDK) | psycopg2 (same) |
| **Migration** | — | Ganti env var saja (host, port, password) |

**Justifikasi**: PostgreSQL dipilih karena:
1. Fitur analytics kuat (window functions, JSONB, CTE) — cocok untuk Gold layer aggregation
2. Low-latency serving (< 5ms) dibanding BigQuery (~1-3s per query)
3. Tidak ada vendor lock-in — pure psycopg2 driver, bisa pindah provider tanpa ubah code
4. Ecosystem mature — indexing, connection pooling, `pg_stat_statements`, backup/restore standard

### Alternatif yang Dipertimbangkan

| Alternatif | Alasan Tidak Dipilih |
|-----------|---------------------|
| MySQL | PostgreSQL lebih kuat untuk analytics (window functions, JSONB) |
| MongoDB | Data relasional, tidak cocok untuk document store |
| Redis | Hanya untuk caching, bukan primary store |
| SQLite | Tidak cocok untuk concurrent access di production |
| Supabase SDK | Vendor lock-in; pure psycopg2 lebih portable |
| DuckDB | Pernah dipakai di awal project, tapi tidak cocok untuk multi-user serving |

---

## 5. Data Pipeline

| Technology | Version | Fungsi | Justifikasi |
|-----------|---------|--------|-------------|
| **Kestra** | 1.3.19 | Orchestration | Ringan (2 containers vs Airflow 4), YAML flows, visual UI, retry built-in |
| **dbt** (dbt-bigquery) | ≥ 1.8.0 | SQL transforms (Silver → Gold) | Modular, testable, version controlled, community besar |
| **python-holidays** | ≥ 0.50 | Hari besar Indonesia | Offline, reliable, 91 rows (2024-2027) |
| **pandas** | ≥ 2.0.0 | Data manipulation di ETL | Standard library untuk data processing |
| **BeautifulSoup** + **lxml** | ≥ 4.12 / ≥ 5.0 | HTML parsing (PIHPS scraper) | Robust untuk parsing response BI PIHPS |
| **tenacity** | ≥ 8.0.0 | Retry logic | Decorator-based, flexible retry strategies |
| **loguru** | ≥ 0.7.0 | ETL logging | Lebih friendly dari stdlib logging, structured output |

### Pipeline Architecture: Medallion

| Layer | Location | Tool | Schedule |
|-------|----------|------|----------|
| **Extract** → Bronze | BigQuery `raw.*` | Python scripts | Daily 07:00 WIB (Kestra) |
| Bronze → **Silver** | BigQuery `staging.*` | dbt (SQL views) | After extract |
| Silver → **Gold** | PostgreSQL `marts.*` + `app.*` | dbt + sync script | After dbt run |

### Alternatif yang Dipertimbangkan

| Alternatif | Alasan Tidak Dipilih |
|-----------|---------------------|
| Prefect | Kurang mature, smaller community |
| Dagster | Bagus tapi learning curve lebih tinggi |
| Cron jobs | Tidak ada UI, sulit monitor, tidak ada retry |
| Stored procedures | Sulit version control, testing, debugging |
| Python transforms (pandas) | dbt SQL lebih deklaratif, testable, dan version-controlled |

---

## 6. Infrastructure

| Technology | Version | Fungsi | Justifikasi |
|-----------|---------|--------|-------------|
| **Docker** | — | Containerization | Reproducible environment, isolasi dependency, portable lintas OS |
| **Docker Compose** | — | Multi-service orchestration | App + ML + Kestra dalam 1 file |
| **Terraform** | ~> 1.9 | Infrastructure as Code | Reproducible BigQuery setup, version controlled |
| **uv** | Latest | Python package manager | 10-100x faster dari pip, lockfile (`uv.lock`) |
| **Git** | — | Version control | Conventional commits, PR workflow |
| **GitHub** | — | Repository hosting | Private repo, free tier |

### Container Strategy

| Service | Image | Port | Profile |
|---------|-------|------|---------|
| `app` | Custom (Python 3.10-slim + uv) | 8000 | Default |
| `ml-model` | Custom (Python + LightGBM) | 8001 | `ml` |
| `kestra` | Custom (Kestra 1.3.19 + Python + dbt-bigquery) | 8080 | `etl` |
| `kestra-postgres` | `postgres:16-alpine` | — | `etl` |

### Terraform Resources

| Resource | Detail |
|----------|--------|
| `google_project_service.bigquery` | Enable BigQuery API |
| `google_bigquery_dataset.raw` | Bronze layer dataset |
| `google_bigquery_dataset.staging` | Silver layer dataset |
| `google_bigquery_table.*` | 8 raw tables (with partitioning + clustering) |

Note: `marts` dataset tidak di-manage Terraform (dev mode). dbt auto-creates jika diperlukan.

### Alternatif yang Dipertimbangkan

| Alternatif | Alasan Tidak Dipilih |
|-----------|---------------------|
| pip | Lambat, no lockfile native, uv superior |
| Poetry | Bagus tapi uv lebih cepat dan simpler |
| Kubernetes | Over-engineering untuk MVP (< 50 users) |
| Pulumi | Terraform lebih mature untuk GCP, HCL readable |
| AWS CDK | Vendor lock-in ke AWS, project pakai GCP |

---

## 7. ML Stack (Managed by ML Teammate)

| Technology | Fungsi | Justifikasi |
|-----------|--------|-------------|
| **LightGBM** | Price prediction (quantile regression) | Fast training, native quantile support, better than XGBoost untuk tabular |
| **Conformal Prediction** | Confidence interval (P10/P90) | Distribution-free, valid coverage guarantee |
| **pandas / Polars** | Feature engineering | Standard data manipulation |
| **scikit-learn** | Preprocessing, evaluation | Mature, well-documented |

### ML Data Contract

| Direction | Table | Database |
|-----------|-------|----------|
| ML reads features from | `mart_modelling_harga_pangan` | PostgreSQL (Gold) |
| ML writes predictions to | `app.ml_predictions` | PostgreSQL (Gold) |

---

## 8. Testing & Quality

| Technology | Version | Fungsi | Justifikasi |
|-----------|---------|--------|-------------|
| **pytest** | ≥ 8.3.0 | Unit testing | Standard Python testing, fixture-based |
| **pytest-asyncio** | ≥ 0.23.0 | Async test support | FastAPI async endpoints |
| **Playwright** | — | E2E testing (planned) | Modern, auto-wait, multi-browser |
| **ruff** | ≥ 0.4.0 | Linting + formatting | 10-100x faster dari flake8 + black |
| **dbt test** | Built-in | Data quality testing | not_null, unique, accepted_values, relationships |

### Test Coverage (Current)

| Suite | Tests | Status |
|-------|-------|--------|
| RCA Engine | 14 tests | ✅ Pass |
| HET Monitor | 14 tests | ✅ Pass |
| Weather Data | 8 tests | ✅ Pass |
| HTML Structure | 40 assertions | ✅ 36/40 pass |
| E2E (Playwright) | 28 test scripts | ⬜ Needs server |
| dbt tests | 17 tests | ✅ Pass |

---

## 9. External Services & APIs

| Service | Fungsi | Cost | Limit |
|---------|--------|------|-------|
| **BI PIHPS** (`bi.go.id/hargapangan`) | Harga harian komoditas | Free | Public data, rate limited |
| **Open-Meteo** (`open-meteo.com`) | Historical weather data | Free | Unlimited (non-commercial) |
| **python-holidays** | Hari besar Indonesia | Free (package) | Offline, no API call |
| **Google BigQuery** | Data warehouse | Free tier | 10 GB + 1 TB/bulan |
| **Supabase** | Managed PostgreSQL (dev/demo) | Free tier | 500 MB, 50K MAU |
| **Google Fonts** | Web fonts (Inter, JetBrains Mono) | Free | CDN |
| **jsDelivr CDN** | Alpine.js, Chart.js delivery | Free | CDN |

---

## 10. Development Tools

| Tool | Fungsi | Justifikasi |
|------|--------|-------------|
| **VS Code** | Primary IDE | Extensions, integrated terminal, Git |
| **Claude Code** | AI pair programming | Code generation, review, documentation |
| **gcloud CLI** | GCP management | BigQuery access, ADC login |
| **git** | Version control | Conventional commits format |
| **Postman / Thunder Client** | API testing | Manual endpoint testing |
| **Browser DevTools** | Frontend debugging | Network tab, console, responsive mode |

---

## 11. Version Matrix

| Component | Version | Pin Type |
|-----------|---------|----------|
| Python | 3.10+ | Minimum |
| FastAPI | 0.115.0 | Exact |
| Uvicorn | 0.30.6 | Exact |
| Pydantic | ≥ 2.8.0 | Minimum |
| psycopg2-binary | ≥ 2.9.9 | Minimum |
| python-jose | 3.3.0 | Exact |
| bcrypt | ≥ 4.0.0 | Minimum |
| google-cloud-bigquery | ≥ 3.41.0 | Minimum |
| dbt-core | ≥ 1.8.0 | Minimum |
| dbt-bigquery | ≥ 1.8.0 | Minimum |
| PostgreSQL | 16 (alpine) | Major |
| Terraform | ~> 1.9 | Minor |
| Google provider | ~> 5.40 | Minor |
| Alpine.js | 3.x | Major (CDN) |
| Chart.js | 4.4.4 | Exact (CDN) |

**Lock file**: `uv.lock` — semua versi exact di-lock untuk reproducibility.

---

## 12. Cost Summary per Technology

| Technology | Dev/Demo | Production | Notes |
|-----------|----------|------------|-------|
| BigQuery | $0 | $0 | Free tier sufficient |
| PostgreSQL (Supabase) | $0 | — | Dev/demo only |
| PostgreSQL (Docker) | — | ~$0 (VPS included) | Production only |
| VPS | $0 (local) | $20-25/bulan | 2 vCPU, 4GB RAM |
| Domain + SSL | $0 | ~$1-2/bulan | Let's Encrypt free |
| All CDNs | $0 | $0 | jsDelivr, Google Fonts |
| All APIs | $0 | $0 | PIHPS, Open-Meteo public |
| **Total** | **$0** | **~$25-30/bulan** | |

# RADAR Pangan — Proposal Scope Reference

**System Name:** R.A.D.A.R Pangan — Real-time Anti-inflation Detection, Analysis & Response  
**Event:** BI Hackathon & Digdaya 2026 — sub-topic "Digitalisasi Ketahanan Pangan"  
**Team:** Simatana (Enzi · Fariz · Rayyan · Rayhan)  
**Stage:** 2nd Submission (working prototype/demo)

---

## Problem Statement

Indonesia's food inflation is driven by 6 volatile commodities (bawang merah, bawang putih, 4 jenis cabai) whose prices spike unpredictably due to weather, seasonal demand, and distribution bottlenecks. Regional inflation control teams (TPID) and Bapanas currently lack an integrated, real-time tool to detect anomalies early, understand root causes, and issue policy responses faster than the crisis appears.

---

## Proposed Solution

A web-based food price intelligence platform with:
1. **Real-time monitoring dashboard** — daily prices vs. HET (government-set ceiling), alert coloring
2. **RCA Engine** — 4-step rule-based root cause diagnosis → policy action narrative
3. **3-Layer ML System** — price forecast + statistical detection + LLM decision agent
4. **Simulate-intervention** — "what if" scenario analysis for market operations
5. **RBAC** — role-gated access (Viewer, Analyst, Admin)

---

## Scope Boundaries (Do Not Exceed These)

### Komoditas (6 only)
| Komoditas | comcat_id |
|---|---|
| Bawang Merah Ukuran Sedang | com_11 |
| Bawang Putih Ukuran Sedang | com_12 |
| Cabai Merah Besar | com_13 |
| Cabai Merah Keriting | com_14 |
| Cabai Rawit Hijau | com_15 |
| Cabai Rawit Merah | com_16 |

### Wilayah (4 Provinsi, 18 Kota)
- **Banten:** Kota Serang, Kota Cilegon, Kota Tangerang
- **Jawa Barat:** Kota Bandung, Kota Cirebon, Kota Tasikmalaya, Kota Bekasi, Kota Bogor, Kota Depok, Kota Sukabumi, Kab. Cirebon, Kab. Tasikmalaya
- **DKI Jakarta:** Kota Jakarta Pusat
- **Sulawesi Selatan:** Kota Makassar, Kota Palopo, Kota Parepare, Kota Watampone, Kab. Bulukumba

### Target Users (B2G + B2B only, no B2C)
- **Primary:** TPID (Tim Pengendalian Inflasi Daerah), Bapanas
- **Secondary:** Bulog, ID Food
- NOT for consumers, retailers, or general public

---

## Architecture Layers

### Data Flow (Medallion)
```
BI PIHPS (harga)  ──┐
Hari Besar         ──┼──> ETL (Airflow + dbt) ──> BigQuery (Bronze + Silver) ──> Supabase PostgreSQL (Gold)
Open-Meteo (cuaca) ──┘                                                                     |
Musim Panen (static) ──────────────────────────────────────────────────────────────────────┘
                                                                                            |
                                                                                    FastAPI (port 8000)
                                                                                            |
                                                                              ML Server (port 8001)
                                                                                            |
                                                                               HTML + Alpine.js frontend
```

### Main App — port 8000 (FastAPI)
Serves the frontend and owns:
- `/api/commodities`, `/api/rca`, `/api/het`, `/api/cuaca` — core data endpoints
- `/api/auth/*` — JWT + RBAC
- `/api/ml/*` — proxy to ML server (port 8001)
- RCA Engine (`src/engine/rca_engine.py`) — rule-based, independent of ML
- HET Monitor (`src/engine/het_monitor.py`)

### ML Server — port 8001 (FastAPI, separate process)
Owns the 3-layer intelligence:
- **Lapis 1 — Forecast:** LightGBM Quantile Regression, 4 models (q50/q90 × t7/t14d)
- **Lapis 2 — Detection:** HET breach classification, CUSUM change-point, Z-score, disparity scoring
- **Lapis 3 — Decision:** LLM ReAct Agent (NVIDIA NIM primary, Groq fallback) with 4 tools:
  - `get_historical_pattern` — seasonal price context
  - `compare_regional_prices` — cross-city disparity
  - `get_upcoming_events` — hari besar + musim panen lookup
  - `get_het_breach_history` — compliance history

### RCA Engine (separate from ML, rule-based)
4-step sequential check, early exit:
1. **Hari Raya** (H-14 to H+3 window) → DiagnosisType.DEMAND
2. **Cuaca Ekstrem** (rain >100mm, drought >14d, temp >38°C, wind >60km/h) → DiagnosisType.SUPPLY
3. **Persebaran Kota** (>60% kota naik serempak) → DiagnosisType.SUPPLY (nasional)
4. **Stok Pedagang** (stok menipis) → DiagnosisType.DISTRIBUSI
5. None triggered → DiagnosisType.UNKNOWN / DiagnosisType.EKSPEKTASI (3 bulan inflasi positif)

### Frontend (6 pages, HTML + Alpine.js + Chart.js)
| Page | URL | Min Role |
|---|---|---|
| Login | `/login` | - |
| Dashboard Monitoring | `/` | Viewer |
| Panduan Analis | `/guide` | - |
| Analisis RCA | `/rca` | Analyst |
| Prediksi ML | `/prediksi` | Analyst |
| Admin | `/admin` | Admin |

---

## Database Tables (Supabase PostgreSQL — Gold Layer)

| Table | Rows | Purpose |
|---|---|---|
| `app.harga_pangan` | 168,691 | Core daily price data (source of truth) |
| `app.cuaca_harian` | 11,605 | Weather by station (Bandung/Cirebon/Jakarta/Makassar/Tangerang) |
| `app.ml_predictions` | growing | Output store from ML pipeline |
| `app.hari_besar` | 91 | National holidays 2024–2027 (python-holidays) |
| `app.musim_panen` | 18 | Harvest season calendar per komoditas + region |
| `app.het_reference` | 0 | HET reference (currently loaded from local CSV) |
| `app.inflasi_bulanan` | 462 | Monthly inflation MTM/YTD by komoditas (dummy data) |
| `app.inflasi_reference` | 152 | Historical inflation reference |
| `app.dashboard_harga_pangan` | 174,290 | Pre-aggregated dashboard view |
| `app.users` | - | RBAC user store (bcrypt passwords) |
| `staging.stg_dim_tanggal` | 1,658 | Date dimension |

---

## ML Features (34 total, as of last train)
Lag features (1d, 7d, 14d, 30d), delta/pct_change (1d, 7d), rolling stats (avg/std/min/max 7d+30d), cross-wilayah (avg_nasional, zscore, ratio), calendar (bulan, kuartal, hari, is_ramadan, is_year_end), HET features (pct_utilization, jarak_ke_het_pct), weather (precip_7d_avg, temp_max_7d), categorical encodings (comcat_id_encoded, kota_id, provinsi_id).

---

## Judging Criteria (6 pillars)
1. **Alignment** — "Digitalisasi Ketahanan Pangan" → volatility detection + policy action
2. **Technical Quality** — Medallion architecture, 3-layer ML, JWT RBAC, Docker, dbt
3. **Effectiveness & Impact** — Measurable KPIs (detection speed, false positive rate, TPID response time)
4. **Business Model** — B2G (Bapanas/TPID SaaS license) + B2B (Bulog, ID Food API)
5. **Uniqueness** — 3-layer ML is novel; most tools only monitor, this recommends
6. **Market Need** — TPID 514 kabupaten/kota; 2024 food inflation 10.9%+ episodes

---

## What Is NOT In Scope
- B2C features (consumer apps, price alerts for shoppers)
- Komoditas beyond the 6 MVP commodities
- Provinces beyond the 4 (Banten, Jabar, DKI, Sulsel)
- Real-time scraping on user request (batch ETL only)
- Social media sentiment analysis
- Supply chain physical tracking / IoT
- Payment or e-commerce integration
- Mobile app (web only)
- BigQuery direct queries at runtime (Supabase serves live traffic)

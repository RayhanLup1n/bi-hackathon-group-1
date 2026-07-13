# R.A.D.A.R Pangan — Revamp Gap Analysis

## TLDR

Revamp R.A.D.A.R Pangan bukan sekadar perubahan tampilan dashboard. PRD dan Business Model Canvas terbaru mengubah produk dari kumpulan fitur monitoring, RCA, dan prediksi menjadi **web-based decision-support platform** untuk analis dan pengambil keputusan TPID.

Target alur produk baru adalah:

```text
DETECT → PRIORITIZE → EXPLAIN → SUGGEST NEXT STEP → HUMAN REVIEW
```

Repository sudah memiliki fondasi teknis penting: FastAPI, PostgreSQL/Supabase serving layer, BigQuery ETL layer, frontend statis, HET/RCA/Bowtie engine, ML inference service, Docker, Railway configuration, dan test suite. Gap terbesar berada pada lapisan keputusan terpadu yang menghubungkan seluruh fondasi tersebut:

- priority score dan confidence gate;
- structured recommendation contract;
- provenance dan transparency layer;
- response options yang aman;
- human review state;
- paket tinjauan bersama;
- agregasi API untuk Executive Dashboard;
- workflow produk yang siap diuji pada pilot institusional.

Dokumen ini membandingkan kondisi repository dengan:

- [`docs/RADAR_Pangan_PRD_MVP.md`](RADAR_Pangan_PRD_MVP.md);
- [`docs/RADAR_Pangan_Business_Model_Canvas.md`](RADAR_Pangan_Business_Model_Canvas.md);
- [`PROJECT_OVERVIEW.md`](../PROJECT_OVERVIEW.md).

## 1. Konteks Revamp

### 1.1 Arah produk baru

| Aspek | Baseline saat ini | Target revamp |
|---|---|---|
| Positioning | Monitoring harga + RCA + prediksi | Decision-support untuk prioritas dan koordinasi TPID |
| Primary user | Viewer/Analyst/Admin secara teknis | Analis/sekretariat TPID |
| Decision user | Belum memiliki workflow khusus | Pimpinan/anggota TPID |
| Unit output | Kartu komoditas, RCA, prediksi, alert | Recommendation/priority package yang dapat ditinjau |
| Prioritas | ML intervention priority 1–5 dan alert level | `raw_priority_score × confidence_factor` |
| Explanation | Narasi RCA/LLM dan hasil engine | Fakta, model output, inference, missing information |
| Response | Rekomendasi/action dari engine lama | Whitelisted response options, bukan instruksi kebijakan |
| Review | Belum ada persistence workflow | Analyst review: Belum Ditinjau, Untuk Dibahas, Ditunda, Ditolak |
| Deployment awal | Local, Docker, Railway demo | Railway untuk validasi awal; private/single-tenant sebagai hardening path |
| Model bisnis | Hackathon/demo | Assisted implementation + maintenance + private/white-label |

### 1.2 Keputusan scope yang sudah dikunci

- Fase yang dianalisis: **MVP sampai pilot**.
- Target pilot: **BI KPw/TPID**.
- Deployment awal: **Railway/demo cloud**.
- Data pilot: **hybrid** — data publik/sanitized untuk analitik utama dan data institusi terbatas pada area yang diizinkan.
- Stack existing dipertahankan; tidak ada rewrite framework.
- Keputusan kebijakan tetap berada pada manusia.
- Railway diperlakukan sebagai validasi awal, bukan baseline final untuk data institusional sensitif.

## 2. Status Classification

| Status | Arti |
|---|---|
| `IMPLEMENTED` | Kemampuan tersedia dan dapat ditelusuri pada source code atau konfigurasi aktif. |
| `PARTIAL` | Sebagian kemampuan tersedia, tetapi belum memenuhi kontrak PRD baru. |
| `MISSING` | Belum ditemukan implementasi yang memenuhi requirement. |
| `CONFLICTING` | Implementasi atau dokumen existing bertentangan dengan keputusan PRD/BMC baru. |
| `UNVALIDATED` | Ada implementasi/hipotesis, tetapi belum memiliki validasi domain, legal, model, atau pilot. |

Status pada dokumen ini adalah hasil static inspection. Status runtime, data aktual, performa query, dan metrik model tetap perlu diverifikasi melalui environment serta pilot test.

## 3. Inventory Baseline Repository

### 3.1 Komponen yang tersedia

| Area | Evidence repository | Status baseline |
|---|---|---|
| Backend | `main.py`, `src/api/` | `IMPLEMENTED` |
| Authentication | `src/api/auth_routes.py`, `src/data/auth_db.py` | `IMPLEMENTED` |
| RBAC | `_current_user`, `_require_admin`, `_require_analyst` | `PARTIAL` — role guard ada, workflow role baru belum lengkap |
| Serving database | `src/data/database.py`, `src/data/commodity_data.py`, `src/data/weather_data.py` | `IMPLEMENTED` |
| BigQuery | `src/data/bigquery_client.py`, ETL scripts | `IMPLEMENTED` sebagai warehouse/ETL dan data-quality path |
| HET monitor | `src/engine/het_monitor.py` | `IMPLEMENTED` |
| RCA | `src/engine/rca_engine.py` | `IMPLEMENTED` |
| FTA/Bowtie | `src/engine/bowtie_engine.py` | `IMPLEMENTED` |
| ML forecasting | `ml/src/train.py`, `ml/src/pipeline.py` | `IMPLEMENTED` |
| ML detection | `ml/src/detect.py` | `IMPLEMENTED` |
| ML reasoning | `ml/src/decide.py` | `IMPLEMENTED`, tetapi governance contract baru belum enforced end-to-end |
| ML API | `ml/serve/api.py` | `IMPLEMENTED` |
| ML proxy | `src/api/ml_routes.py` | `IMPLEMENTED` |
| ETL extraction | `etl/extractors/` | `IMPLEMENTED` |
| ETL orchestration | `etl/kestra/flows/` | `IMPLEMENTED` |
| dbt | `etl/dbt_project/` | `IMPLEMENTED` |
| IaC | `infra/` | `PARTIAL` — tersedia, perlu audit kesesuaian deployment pilot |
| Frontend | `frontend/*.html` | `PARTIAL` — halaman tersedia, tetapi workflow masih terpisah |
| Testing | `tests/`, `tests/e2e/` | `PARTIAL` — fondasi baik, belum mencakup kontrak revamp |
| Deployment | Docker, Railway, Render config | `PARTIAL` — demo path tersedia, pilot hardening belum selesai |

### 3.2 Route existing utama

Backend saat ini menyediakan route untuk:

- `/api/commodities` dan `/api/commodity/{key}`;
- `/api/prices/...`;
- `/api/analysis` dan `/api/analysis/{key}`;
- `/api/bowtie` dan `/api/bowtie/{key}`;
- `/api/het`;
- `/api/cuaca`;
- `/api/stok` sebagai placeholder;
- `/api/predictions`;
- `/api/data-quality`;
- `/api/auth/*`;
- `/api/ml/*`;
- `/health`.

ML service menyediakan:

- `POST /api/v1/analyze`;
- `POST /api/v1/batch`;
- `GET /api/v1/alerts`;
- `GET /api/v1/summary/{tanggal}`;
- `GET /api/v1/komoditas`;
- `GET /api/v1/kota`;
- `POST /api/v1/simulate`;
- `GET /health`.

## 4. Product Workflow Gap

### 4.1 Executive Dashboard

**Requirement PRD:** dashboard harus menampilkan status wilayah, data freshness, jumlah risiko, Top 3 priorities, paket tinjauan, dan confidence data.

**Baseline:** `frontend/index.html` sudah menampilkan dashboard, commodity cards, HET, ML alerts, RCA/Bowtie summary, dan chart mini. Namun dashboard masih mengorkestrasi banyak endpoint dan belum menggunakan satu decision object terpadu.

**Status:** `PARTIAL`

**Gap:**

- belum ada `/api/mvp/overview`;
- belum ada Top 3 berdasarkan priority score baru;
- belum ada status pipeline dan provenance terpadu;
- belum ada confidence data sebagai summary metric;
- belum ada paket tinjauan bersama;
- dashboard masih bercampur antara konsep lama dan konsep revamp.

**Prioritas:** P0.

### 4.2 Ranked Priority Queue

**Requirement PRD:** daftar komoditas/wilayah terurut berdasarkan score deterministik dengan rank, kondisi harga, risiko, horizon, confidence, response system, dan alasan ringkas.

**Baseline:** ML `FullAnalysisResult` memiliki alert level dan `intervention_priority` 1–5. `ml/src/pipeline.py` dapat mengurutkan hasil analisis berdasarkan priority. Backend memiliki alert endpoint.

**Status:** `PARTIAL`

**Gap:**

- skala lama 1–5 belum sama dengan score 0–100;
- belum ada confidence factor dari freshness, coverage, history, dan model performance;
- belum ada `display_priority_score`;
- belum ada response system taxonomy `Monitor`, `Verifikasi`, `Koordinasikan`, `Pertimbangkan Intervensi`;
- belum ada endpoint priority queue yang stabil untuk frontend.

**Prioritas:** P0.

### 4.3 Detail Prioritas Berbasis Bukti

**Requirement PRD:** urutan detail harus memisahkan fakta, output model, faktor yang mungkin berkontribusi, missing information, response options, dan sumber/metodologi.

**Baseline:** halaman RCA dan Prediksi tersedia terpisah. RCA memiliki check results, diagnosis, severity, dan action. Prediksi memiliki forecast, SHAP, alert, dan rekomendasi ML.

**Status:** `PARTIAL`

**Gap:**

- pengguna masih berpindah antara `/analysis` dan `/prediksi`;
- belum ada recommendation object bersama;
- fakta, model output, dan inference belum memiliki type contract yang konsisten;
- missing information belum menjadi blok wajib;
- sumber, cutoff, dan model metric belum tampil sebagai satu evidence layer.

**Prioritas:** P0.

### 4.4 Human Review State

**Requirement PRD:** Analyst dapat menyimpan status `Belum Ditinjau`, `Untuk Dibahas`, `Ditunda`, atau `Ditolak` beserta reviewer, timestamp, note, dan snapshot rekomendasi.

**Baseline:** authentication dan role guard tersedia. Tidak ditemukan route atau tabel `decision_review` pada source code saat audit.

**Status:** `MISSING`

**Gap:**

- belum ada persistence review;
- belum ada endpoint POST review;
- belum ada snapshot recommendation;
- belum ada audit trail perubahan status;
- role Analyst belum memiliki action review yang terdefinisi.

**Prioritas:** P0.

### 4.5 Paket Tinjauan Bersama

**Requirement PRD:** mengelompokkan minimal dua komoditas/wilayah dengan risiko tinggi/kritis, klaster wilayah sama, dan horizon yang tumpang tindih.

**Baseline:** ML alert dan summary dapat mengurutkan kombinasi komoditas/kota. Belum ditemukan grouping engine atau output paket.

**Status:** `MISSING`

**Gap:**

- belum ada grouping rule;
- belum ada bundle schema;
- belum ada alasan pengelompokan;
- belum ada missing information per bundle;
- belum ada UI bundle.

**Prioritas:** P1 untuk MVP jika timebox ketat; P0 untuk demo utama sesuai PRD.

## 5. Decision Contract Gap

### 5.1 Structured recommendation object

PRD menetapkan object minimal dengan field:

```text
recommendation_id
commodity
region
price_condition
risk_level
time_horizon_days
confidence
observed_facts[]
model_outputs[]
possible_factors[]
next_step
response_options[]
missing_information[]
sources[]
knowledge_status
requires_human_review
```

**Baseline:** object existing tersebar pada `CommodityData`, `RCAResult`, `BowtieResult`, `FullAnalysisResult`, dan `DecisionResult`. Masing-masing object masih memiliki naming, status, dan tujuan berbeda.

**Status:** `MISSING` sebagai contract terpadu; `PARTIAL` sebagai bahan pembentuk.

**Rekomendasi:** buat domain response model baru yang menjadi contract utama MVP. Object lama tetap dipakai sebagai internal input selama masa transisi, tetapi tidak menjadi response utama Executive Dashboard.

### 5.2 Priority score

PRD menetapkan bobot awal:

| Komponen | Bobot |
|---|---:|
| Posisi harga terhadap ambang | 25% |
| Risiko forecast P90 melampaui ambang | 30% |
| Momentum/anomali/change point | 20% |
| Persebaran kenaikan regional | 15% |
| Cuaca/kalender | 10% |

Formula target:

```text
raw_priority_score = weighted risk components
display_priority_score = raw_priority_score × confidence_factor
```

**Baseline:** HET monitor, ML alert, disparity, change point, weather, dan calendar signal tersedia secara terpisah. Belum ditemukan engine yang menghitung formula baru.

**Status:** `MISSING`

**Catatan:** bobot dan kategori score adalah `INTERNAL_HYPOTHESIS`. Kode harus menyimpan konfigurasi/version, bukan menanamkannya pada UI.

### 5.3 Confidence gate

PRD menetapkan confidence berdasarkan freshness, coverage, history, dan model performance. Belum ditemukan satu gate yang diterapkan pada seluruh response.

**Status:** `MISSING`

**Dampak:** sistem belum dapat membatasi response option ketika data stale, coverage rendah, atau model underperform.

**Prioritas:** P0.

### 5.4 Response options dan guardrail

**Baseline:** engine existing menghasilkan `action` dan ML LLM dapat menghasilkan `rekomendasi`. ML juga memiliki rule-based decision fallback.

**Status:** `PARTIAL` dan `CONFLICTING` terhadap PRD baru.

**Conflict utama:** sebagian output existing menggunakan bahasa rekomendasi intervensi yang lebih spesifik daripada batas baru PRD. PRD mengharuskan response options berbasis whitelist dan melarang instruksi kebijakan otomatis.

**Perubahan yang dibutuhkan:**

- response options berasal dari deterministic rule engine;
- LLM hanya merangkum structured object;
- tidak boleh mengarang volume, anggaran, lokasi, supplier, kewenangan, atau jadwal;
- fallback LLM menggunakan template terstruktur;
- `requires_human_review=true` menjadi default untuk recommendation.

## 6. API Gap

### 6.1 Target endpoint MVP

| Endpoint | Kondisi saat ini | Status |
|---|---|---|
| `GET /api/mvp/overview` | Belum ditemukan | `MISSING` |
| `GET /api/mvp/priorities` | Belum ditemukan; ada `/api/ml/alerts` dan `/api/ml/summary` | `MISSING` |
| `GET /api/mvp/priorities/{recommendation_id}` | Belum ditemukan | `MISSING` |
| `POST /api/mvp/priorities/{recommendation_id}/review` | Belum ditemukan | `MISSING` |
| `GET /api/mvp/transparency` | Belum ditemukan | `MISSING` |
| `GET /api/mvp/service-status` | Belum ditemukan; health route terpisah | `PARTIAL` |

### 6.2 Contract strategy

Backend perlu memiliki orchestration layer baru yang:

1. mengambil data serving dan output engine existing;
2. menerapkan data-quality/confidence gate;
3. menghitung priority score;
4. membentuk structured recommendation;
5. membentuk review bundle;
6. mengembalikan response agregat untuk frontend.

Orchestration layer tidak boleh memindahkan business logic ke HTML. Frontend cukup mengonsumsi contract MVP dan menangani state loading, empty, stale, unavailable, serta error.

### 6.3 Backward compatibility

Route existing tetap dipertahankan selama masa transisi karena halaman existing dan test saat ini masih menggunakannya. Route `/api/mvp/*` menjadi contract baru untuk workflow revamp. Migration dari route lama dilakukan setelah workflow baru stabil.

## 7. Database dan Auditability Gap

### 7.1 Tabel yang sudah ada atau dirujuk

Repository dan dokumentasi merujuk pada:

- `app.harga_pangan`;
- `app.cuaca_harian`;
- `app.ml_predictions`;
- `app.hari_besar`;
- `app.musim_panen`;
- `app.het_reference`;
- `app.users`;
- data inflasi/reference;
- dashboard dan modelling marts.

### 7.2 Tabel baru minimum

PRD mengusulkan `decision_review`:

| Field | Kegunaan |
|---|---|
| `id` | Identitas review |
| `recommendation_id` | Relasi ke recommendation snapshot |
| `status` | Status review |
| `reviewer_user_id` | User Analyst/Admin |
| `note` | Alasan atau catatan |
| `recommendation_snapshot` | Snapshot object saat review |
| `created_at` | Waktu dibuat |
| `updated_at` | Waktu diubah |

**Status:** `MISSING`

### 7.3 Metadata recommendation

Recommendation perlu membawa atau merujuk pada:

- `recommendation_id`;
- `data_cutoff`;
- `pipeline_run_id`;
- `ingested_at`;
- `coverage_ratio`;
- `missing_count`;
- `imputation_status`;
- `model_version`;
- priority configuration version;
- knowledge status.

**Status:** `PARTIAL` — beberapa metadata seperti `model_version` tersedia pada prediction store, tetapi belum menjadi metadata terpadu pada output decision.

### 7.4 Data ownership dan pilot hybrid

Untuk Railway hybrid pilot, data boundary perlu ditetapkan sebelum integrasi data institusi:

- data publik/sanitized boleh dipakai pada dataset demo;
- data terbatas hanya boleh masuk jika ada izin dan akses yang jelas;
- data restricted tidak boleh tercampur pada log, error message, screenshot, atau LLM prompt tanpa policy;
- data tenant/institusi harus dapat dihapus atau diekspor sesuai perjanjian;
- penggunaan logo/nama institusi memerlukan persetujuan terpisah.

**Status:** `UNVALIDATED` secara legal dan operasional.

## 8. Data Quality dan Provenance Gap

### 8.1 Kemampuan existing

`src/data/data_quality.py` sudah menyediakan pemeriksaan coverage, missing dates, outliers, duplicates, dan quality summary. Admin-only data-quality routes juga tersedia.

### 8.2 Gap terhadap PRD

| Requirement | Baseline | Status |
|---|---|---|
| Freshness ditampilkan pada kartu prioritas | Quality/query capability ada, UI contract belum | `PARTIAL` |
| Coverage ratio | Admin data quality ada | `PARTIAL` |
| Missing count | Ada pada quality path, belum decision contract | `PARTIAL` |
| Imputation/fallback status | Belum konsisten di response utama | `MISSING` |
| Pipeline run ID | Ada logging pada ETL tertentu, belum diteruskan ke recommendation | `PARTIAL` |
| Source version | Belum menjadi field wajib | `MISSING` |
| Model version | Ada pada prediction persistence | `PARTIAL` |
| Data stale membatasi response | Belum ada central gate | `MISSING` |
| Source mismatch memblokir publish | Belum ditemukan | `MISSING` |

### 8.3 Prioritas implementasi

Data quality harus menjadi input decision layer, bukan hanya halaman admin. Minimum P0 adalah freshness, coverage, missing count, data cutoff, dan service status pada overview/detail.

## 9. ML dan AI Gap

### 9.1 Yang sudah tersedia

- LightGBM quantile model untuk P50/P90 dan horizon 7/14 hari;
- feature engineering historis, HET, calendar, weather, dan regional;
- change point/CUSUM, HET alert, dan disparity detection;
- rule-based decision fallback;
- optional LLM reasoning agent;
- ML health endpoint;
- persistence prediction ke `app.ml_predictions`;
- simulation endpoint.

### 9.2 Gap model governance

| Requirement | Status |
|---|---|
| Baseline last-value/moving/seasonal naive | `UNVALIDATED` — perlu evidence backtest aktual |
| MAE/WAPE P50 | `PARTIAL` — helper evaluasi ada, hasil terpadu belum menjadi transparency output |
| Pinball loss | `IMPLEMENTED` pada training helper, belum dipublikasikan sebagai contract |
| Empirical P90 coverage | `IMPLEMENTED` pada training helper, belum dipublikasikan sebagai contract |
| Breakdown per komoditas | `UNVALIDATED` |
| Model version dan training cutoff | `PARTIAL` |
| Underperform fallback | `PARTIAL` — perlu central policy |
| History insufficient abstention | `PARTIAL` |
| Data stale membatasi recommendation | `MISSING` |
| LLM hanya merangkum structured object | `CONFLICTING/PARTIAL` — existing agent masih membangun recommendation narrative |
| RAG corpus terotorisasi | `MISSING` sebagai feature MVP/P1 |

### 9.3 Keputusan arsitektur

ML tidak boleh menjadi satu-satunya sumber priority score. Urutan target:

```text
Data Aktual
  → Forecast/Detection
  → Deterministic Prioritization
  → Response Option Rules
  → Structured Recommendation
  → Optional LLM/RAG Explanation
  → Human Review
```

Dengan urutan ini, dashboard tetap berfungsi ketika LLM atau ML offline dan recommendation dapat diuji tanpa nondeterminism LLM.

## 10. Frontend dan Information Architecture Gap

### 10.1 Halaman existing

| Existing page | Kondisi |
|---|---|
| `login.html` | Login dan JWT localStorage tersedia |
| `index.html` | Dashboard monitoring dan integrasi banyak endpoint |
| `rca.html` | RCA/FTA/Bowtie detail |
| `prediksi.html` | Forecast, SHAP, ML status, dan prediction history |
| `guide.html` | Panduan pengguna |
| `admin.html` | User management |

### 10.2 Target halaman revamp

| Target page | Pendekatan |
|---|---|
| Executive Dashboard | Revamp `index.html` menggunakan `/api/mvp/overview` |
| Detail Prioritas | Buat view terpadu atau extend `index.html`; jangan memaksa user berpindah antara RCA dan Prediksi |
| Transparency | Tambahkan panel/page berbasis `/api/mvp/transparency` |
| Admin | Extend `admin.html` untuk review/data quality bila diperlukan |
| Login | Pertahankan dengan perbaikan copy/role handling bila perlu |

### 10.3 Status

`PARTIAL` dan `CONFLICTING` terhadap information architecture baru. Route `/analysis` dan `/prediksi` masih boleh dipertahankan sebagai compatibility/detail views, tetapi happy path harus terlihat sebagai satu workflow.

## 11. Testing Gap

### 11.1 Test yang sudah ada

- HET engine;
- RCA engine;
- Bowtie engine;
- weather data;
- Pydantic schemas;
- HTML structure;
- login;
- dashboard;
- RCA page;
- navigation;
- responsive behavior;
- RBAC.

### 11.2 Test yang belum ada untuk revamp

| Test | Prioritas |
|---|---|
| Priority score weights dan boundary | P0 |
| Confidence factor dan stale gate | P0 |
| Structured recommendation schema | P0 |
| Response option whitelist | P0 |
| Fact/model/inference separation | P0 |
| `decision_review` persistence | P0 |
| Review authorization | P0 |
| `/api/mvp/overview` contract | P0 |
| ML/LLM timeout fallback | P0 |
| Data source unavailable state | P0 |
| Bundle grouping rules | P1 |
| Transparency output | P1 |
| 10–15 AI guardrail scenarios | P1 |
| Usability task: identify priority in 60 seconds | Pilot |
| Hybrid data boundary/security test | Pilot |

### 11.3 E2E target

Test utama yang harus tersedia:

```text
Login Analyst
  → open Executive Dashboard
  → see Top 3 priority
  → open detail
  → distinguish fact/model/inference
  → see next step and missing information
  → submit human review
  → reload and verify persisted review
```

## 12. Deployment dan Operations Gap

### 12.1 Railway demo baseline

Yang sudah tersedia:

- `railway.toml` untuk aplikasi;
- `ml/railway.toml` untuk ML service;
- Dockerfile aplikasi dan ML;
- environment-based credential configuration;
- `/health` pada app dan ML;
- ML offline graceful degradation pada frontend/backend path.

Status: `PARTIAL`.

### 12.2 Gap untuk hybrid pilot

- pemisahan data publik dan restricted data;
- service-to-service authentication antara app dan ML;
- secret rotation;
- backup/restore procedure;
- database migration process;
- structured application logs tanpa data sensitif;
- monitoring latency dan error rate;
- alerting pipeline dan ML health;
- deployment rollback;
- environment separation demo/staging/pilot;
- access review dan user offboarding;
- retention/deletion policy;
- documented incident response.

### 12.3 Pilot readiness boundary

Railway dapat dipakai untuk:

- demo;
- usability test;
- sanitized/public dataset;
- proof-of-value.

Railway tidak boleh dianggap otomatis memenuhi kebutuhan private institutional deployment. Sebelum data restricted digunakan, harus ada keputusan tentang private cloud, network boundary, credential policy, data rights, dan contractual responsibility.

## 13. Business dan Product Operations Gap

### 13.1 BMC yang sudah jelas

- primary buyer hypothesis: BI KPw, TPID, atau pemerintah daerah;
- primary user: analis/sekretariat TPID;
- decision user: pimpinan/anggota TPID;
- delivery: private web application dan white-label;
- hubungan awal: high-touch assisted onboarding;
- revenue hypothesis: pilot/implementation fee, maintenance, white-label, custom analytics;
- partner: domain, data, technology, dan scale partner;
- validasi bisnis: belum ada willingness-to-pay atau pilot formal.

### 13.2 Gap operasional

| Capability | Status |
|---|---|
| Pilot onboarding checklist | `MISSING` |
| User training material | `PARTIAL` — `guide.html` ada, belum pilot-specific |
| Region/commodity configuration | `PARTIAL` |
| Data access agreement template | `MISSING` |
| Branding/white-label approval flow | `MISSING` |
| Support channel and SLA | `MISSING` |
| Model/data review cadence | `MISSING` |
| Pilot outcome report | `MISSING` |
| Pricing interview instrument | `MISSING` |
| Procurement path | `UNVALIDATED` |
| Incident and escalation process | `MISSING` |

### 13.3 Business assumptions yang harus diuji

- analis benar-benar membutuhkan ranking, bukan hanya dashboard;
- ringkasan satu menit sesuai dengan pola kerja decision user;
- paket tinjauan beberapa komoditas memiliki nilai;
- LightGBM memberikan nilai tambah dibanding baseline;
- response options aman tanpa playbook resmi;
- institusi bersedia membayar setup dan maintenance;
- data dapat digunakan untuk deployment komersial;
- white-label lebih realistis daripada public SaaS awal.

## 14. Prioritas Revamp

### 14.1 P0 — MVP decision workflow

1. Tetapkan domain schema recommendation.
2. Implementasikan priority score dan confidence gate.
3. Buat response-option rule engine yang aman.
4. Buat orchestration service untuk overview/priorities/detail.
5. Buat endpoint `/api/mvp/*` minimum.
6. Buat tabel `decision_review` dan persistence review.
7. Revamp dashboard menjadi Executive Dashboard.
8. Buat detail prioritas berbasis evidence.
9. Tampilkan freshness/provenance minimum.
10. Implementasikan ML/LLM/data fallback state.
11. Tambahkan unit, contract, dan E2E tests.

### 14.2 P1 — Pilot quality

1. Paket tinjauan bersama.
2. Transparency page lengkap.
3. Baseline model evaluation dan public metrics.
4. Guardrail scenario suite 10–15 kasus.
5. Usability test minimal tiga pengguna.
6. Snapshot comparison hari ini vs sebelumnya.
7. Executive brief/print view bila dibutuhkan pilot.
8. Pilot onboarding dan support materials.

### 14.3 P2 — Scale readiness

1. Config-driven region/commodity/threshold.
2. White-label branding configuration.
3. Private/single-tenant deployment.
4. Tenant and data isolation.
5. Operational SLA dan support tooling.
6. RAG-lite dengan corpus terotorisasi.
7. Outcome tracking.
8. API/commercial tier.

## 15. Dependency Map

```text
Source/data provenance
        │
        ├──> Data quality gate ───────┐
        │                             │
Forecast + detection ────────────────┤
        │                             v
HET/RCA/Bowtie/context ───> Priority engine
                                      │
                                      v
                          Structured recommendation
                                      │
                ┌─────────────────────┼─────────────────────┐
                v                     v                     v
       Response options       Review persistence      Review bundles
                │                     │                     │
                └──────────────> Executive Dashboard <─────┘
                                      │
                                      v
                              Pilot metrics/audit
```

Dependency rules:

- frontend tidak boleh dibangun final sebelum recommendation contract disepakati;
- response options tidak boleh bergantung pada LLM;
- human review tidak boleh menyimpan recommendation tanpa snapshot/version metadata;
- confidence gate harus dipakai sebelum response options dibentuk;
- bundle hanya boleh dibentuk dari recommendation yang memiliki confidence memadai;
- transparency output harus berasal dari metadata yang dapat ditelusuri, bukan copy manual;
- pilot metrics harus mengambil data dari review/audit event yang persisten.

## 16. Rencana Fase MVP sampai Pilot

### Fase 0 — Contract freeze dan audit

**Tujuan:** menyepakati schema, taxonomy, score, dan source mapping sebelum coding.

**Output:**

- recommendation schema;
- risk/condition/response taxonomy;
- source-to-field mapping;
- priority configuration;
- fallback matrix;
- keputusan data publik versus restricted.

### Fase 1 — MVP build, 7–10 hari kerja

Urutan kerja:

1. Audit endpoint, data, frontend, dan model.
2. Bangun schema dan priority engine.
3. Bangun provenance/confidence gate.
4. Bangun endpoint agregasi.
5. Bangun Executive Dashboard.
6. Bangun detail evidence.
7. Bangun response options dan human review.
8. Tambahkan bundle dan fallback sesuai waktu.
9. Jalankan integration test, guardrail test, dan usability rehearsal.

### Fase 2 — Pilot readiness

Sebelum pilot dengan BI KPw/TPID:

- sanitized/public dataset dan restricted-data boundary jelas;
- user roles dan access review siap;
- data freshness dan pipeline status terlihat;
- model metrics dan limitation tersedia;
- support/onboarding guide tersedia;
- incident/rollback plan tersedia;
- pilot success metrics disepakati;
- branding dan disclaimer disetujui;
- data usage dan retention disepakati.

### Fase 3 — Pilot 4–8 minggu

Yang diukur:

- time-to-understand top priority;
- waktu analisis sebelum/sesudah;
- priority cards reviewed;
- review acceptance/defer/reject;
- false positive;
- data freshness dan coverage;
- relevansi paket tinjauan;
- model performance versus baseline;
- support issue dan adoption;
- willingness-to-pay dan procurement signal.

## 17. Blocker dan Risiko Utama

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Scope terlalu besar untuk 7–10 hari | MVP tidak selesai | freeze P0; P1/P2 dipisahkan |
| Structured contract belum disepakati | FE/BE/ML menghasilkan object berbeda | contract freeze sebelum implementasi |
| Model lebih buruk dari baseline | trust turun | backtest, baseline, confidence rendah/abstain |
| Data stale/missing | confidence palsu | central quality gate |
| LLM menghasilkan instruksi kebijakan | risiko governance | rule whitelist, structured input, fail closed |
| Stok/logistik tidak tersedia | response terlalu generik | tampilkan missing information dan batasi next step |
| Railway dipakai untuk data sensitif tanpa boundary | risiko legal/security | sanitized-first, restricted data hanya dengan izin |
| Existing route dan new route konflik | regressions | backward compatibility dan contract tests |
| BMC assumptions belum tervalidasi | produk tidak fit dengan buyer | pilot interviews dan outcome metrics |
| Sponsor dianggap endorsement resmi | reputational/legal risk | disclaimer dan approval branding |

## 18. Definition of Done untuk Gap Analysis

- [x] PRD dan BMC terbaru dipetakan ke baseline repository.
- [x] Existing component dan route utama diinventarisasi.
- [x] Gap product workflow diidentifikasi.
- [x] Gap decision contract dan API diidentifikasi.
- [x] Gap database, provenance, ML governance, frontend, testing, deployment, dan operations diidentifikasi.
- [x] Setiap gap diberi status classification.
- [x] Gap diprioritaskan menjadi P0, P1, P2, atau assumption.
- [x] Dependency map MVP sampai pilot dibuat.
- [x] Risiko dan blocker utama dicatat.
- [x] Tidak ada perubahan kode, schema, deployment, atau data pada tahap analisis ini.

## 19. Kesimpulan

Fondasi R.A.D.A.R Pangan sudah cukup untuk membangun revamp tanpa rewrite. Strategi yang paling aman adalah menambahkan **decision layer** di atas engine dan data access existing, lalu memindahkan frontend ke contract agregasi baru secara bertahap.

Prioritas utama bukan menambah model baru, melainkan membuat output existing menjadi satu object keputusan yang:

- deterministik pada bagian ranking dan response options;
- transparan pada sumber, freshness, coverage, dan model version;
- membedakan fakta, output model, dan inference;
- aman ketika data atau service gagal;
- dapat ditinjau dan disimpan manusia;
- dapat diukur selama pilot.

Dengan pendekatan tersebut, Railway dapat dipakai untuk proof-of-value hybrid secara terkendali, sementara kebutuhan private deployment, white-label, dan institutional operations dapat dibangun sebagai hardening path setelah problem-solution fit mulai tervalidasi.


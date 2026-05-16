# Project Breakdown — R.A.D.A.R Pangan

> Updated: 16 Mei 2026 | Demo: 4 Juni 2026 (< 3 minggu)
> Stage: **Development / Demo** (Supabase PostgreSQL sebagai Gold layer)
> Prinsip: **Functionality first** → Security later
> Referensi: [NEED_TO_FIX.md (legacy)](NEED_TO_FIX.md) | [PRD](prd/PRD.md) | [FRD](frd/FRD.md) | [ERD](erd/ERD.md) | [SDA](sda/SYSTEM_DESIGN.md)

---

## Status Saat Ini

| Area | Status | Catatan |
|------|--------|---------|
| Data Pipeline (ETL + dbt) | ✅ Working | 619K rows harga, 11K cuaca, 91 hari besar |
| RCA Engine | ✅ Working | 4-step check, 36 unit tests pass |
| HET Monitor | ✅ Working | 14 unit tests pass |
| Auth (JWT + RBAC) | ✅ Working | Frontend guard ada, backend guard belum |
| Frontend 6 pages | ⚠️ Partial | Ada tapi masih inline CSS, guide.html outdated |
| BigQuery → Supabase PostgreSQL migration | ❌ Belum | **BLOCKER** — FE masih query BQ langsung |
| Documentation | ✅ Done | PRD, FRD, ERD, SDA, Tech Stack, Wireframe |

---

## P0 — BLOCKER: Migrate Data Access ke Supabase PostgreSQL (Gold)

> **Mengapa ini P0?** Saat ini semua data di-query langsung dari BigQuery. Teammate tanpa GCP access tidak bisa develop/test frontend. Ini memblokir kolaborasi tim.
>
> **Target**: Pindahkan semua user-facing queries dari BigQuery → Supabase PostgreSQL (yang sudah jalan dan bisa diakses seluruh tim).

### B-01: Sync Gold layer data ke Supabase PostgreSQL ⬜

**Problem**: `commodity_data.py`, `weather_data.py`, `rca_engine.py` semuanya call `bq_query()` langsung. Setiap user request = BigQuery API call (lambat + perlu GCP credentials).

**Solution**: Buat sync script yang copy data dari BigQuery (Silver) → Supabase PostgreSQL (Gold), lalu ubah data layer untuk baca dari Supabase.

**Tasks**:
1. Buat `etl/scripts/sync_gold_to_postgres.py` — export marts.* dari BigQuery → insert ke Supabase PostgreSQL
2. Buat tabel di Supabase: `marts.mart_dashboard_harga_pangan`, `marts.mart_dashboard_ringkasan_nasional`, `marts.mart_modelling_harga_pangan`
3. Sync data hari besar + cuaca ke Supabase juga (untuk RCA)
4. **Effort**: 2-3 jam

### B-02: Migrate `commodity_data.py` → baca dari Supabase ⬜

**Problem**: 5x `bq_query()` calls — setiap page load Dashboard = 5 BigQuery API calls.

**Files**: `src/data/commodity_data.py`

**Tasks**:
1. Ganti `from src.data.bigquery_client import bq_query` → `from src.data.database import db_cursor`
2. Ubah semua SQL dari BigQuery dialect ke PostgreSQL
3. Query dari `marts.mart_dashboard_harga_pangan` (Gold) instead of `raw.harga_pangan` (Bronze)
4. **Effort**: 1-2 jam

### B-03: Migrate `weather_data.py` → baca dari Supabase ⬜

**Problem**: 2x `bq_query()` calls — setiap RCA analysis = BigQuery API call.

**Files**: `src/data/weather_data.py`

**Tasks**:
1. Sync tabel `cuaca_harian` ke Supabase PostgreSQL (Gold layer)
2. Ganti query ke PostgreSQL via `db_cursor()`
3. **Effort**: 1 jam

### B-04: Migrate `rca_engine.py` hari besar → baca dari Supabase ⬜

**Problem**: 1x `bq_query()` call — hari besar calendar di-load dari BigQuery.

**Files**: `src/engine/rca_engine.py:131-133`

**Tasks**:
1. Sync tabel `hari_besar` ke Supabase PostgreSQL (Gold layer)
2. Ganti `bq_query()` → `db_cursor()` query
3. In-memory cache tetap dipertahankan (loaded at startup)
4. **Effort**: 30 menit

### B-05: Update `bigquery_client.py` — hanya untuk ETL ⬜

**Problem**: Setelah B-02/B-03/B-04, BigQuery client seharusnya hanya dipakai oleh ETL pipeline, bukan oleh user-facing code.

**Tasks**:
1. Remove `bigquery_client` import dari `commodity_data.py`, `weather_data.py`, `rca_engine.py`
2. `data_quality.py` boleh tetap pakai BigQuery (admin-only, bukan user-facing)
3. Update `main.py` lifespan — tidak perlu init BigQuery client saat app startup (opsional, hanya untuk ETL)
4. **Effort**: 30 menit

**Total effort B-01 sampai B-05**: ~5-7 jam (1 hari kerja)

**Setelah selesai**:
- ✅ Semua UI data dari Supabase PostgreSQL (< 200ms latency vs 1-3s BigQuery)
- ✅ Teammate bisa develop tanpa GCP access
- ✅ BigQuery hanya untuk ETL batch (Bronze → Silver → sync Gold ke Supabase)

---

## P1 — Functionality untuk Demo

> Task yang harus selesai agar demo berjalan smooth.

### F-01: Extract inline CSS → external stylesheet ⬜

**Files**: Semua `frontend/*.html`
**Tasks**:
1. Buat `frontend/css/style.css` — extract semua CSS dari `<style>` tags
2. Setiap HTML file: hapus `<style>` block, tambah `<link rel="stylesheet" href="/css/style.css">`
3. Konsolidasi CSS variables (`:root`) — saat ini ada minor perbedaan antar file
4. **Effort**: 2-3 jam

### F-02: Update `guide.html` (outdated) ⬜

**File**: `frontend/guide.html`
**Issues**:
- Masih sebut BMKG → harus **Open-Meteo**
- Menyebut 6 checks → harus **4 checks**
- Token key `rca_token` → harus `token`
- Design glassmorphism → harus **neobrutalism**
- Copyright 2025 → **2026**
- Menyebut Beras dan Ayam → harus **6 komoditas MVP** saja
**Effort**: 1-2 jam

### F-03: Navigation antar halaman ⬜

**Problem**: Belum ada nav links konsisten di semua halaman.
**Tasks**:
1. Buat shared nav component (Dashboard, Guide, RCA, Prediksi, Admin — conditional per role)
2. Terapkan di semua 6 halaman
3. Mobile: hamburger menu
4. **Effort**: 1-2 jam

### F-04: Chart.js integration di prediksi page ⬜

**File**: `frontend/prediksi.html`
**Tasks**:
1. Chart.js sudah di-load (CDN), tapi belum dipakai
2. Implement line chart: harga aktual (solid) + prediksi (dashed) + confidence interval (shaded)
3. Data dari `/api/predictions` + `/api/prices/{comcat_id}/history`
4. **Effort**: 2-3 jam

### F-05: Dashboard tambah prediksi ringkas + RCA alert ⬜

**File**: `frontend/index.html`
**Tasks** (sesuai FRD section 4):
1. Tambah komponen **RCA Alert Summary** (komoditas anomali + diagnosis)
2. Tambah **Prediksi Ringkas** di setiap kartu komoditas (trend 7 hari)
3. Tambah **Summary Cards** (rata-rata perubahan, alert count, prediksi naik count)
4. **Effort**: 2-3 jam

### F-06: Buat `config/constants.py` — single source of truth ⬜

**Problem**: MVP komoditas IDs duplikat di 3 tempat.
**Files**:
- `etl/config/constants.py` → `MVP_COMCAT_IDS` (list)
- `src/data/commodity_data.py` → `MVP_KOMODITAS_FILTER` (set)
- `src/data/data_quality.py` → `_MVP_COMCAT` (tuple)

**Tasks**:
1. Buat `config/constants.py` — definisikan semua shared constants
2. Import dari satu tempat di semua file
3. Hapus duplikat
4. **Effort**: 30 menit

### F-07: Fix bugs yang affect demo flow ⬜

| Bug | File | Fix | Effort |
|-----|------|-----|--------|
| Division by zero (`price_prev=0`) | `rca_engine.py:333` | Guard with `if price_prev == 0` | 5 min |
| Division by zero (`kota_list` empty) | `rca_engine.py:215` | Guard with `if total_kota == 0` | 5 min |
| HET KRITIS unreachable | `het_monitor.py:66-73` | Fix threshold logic | 10 min |
| Bare `except` hides errors | `routes.py:326-328` | Catch specific exception | 10 min |

**Total effort**: 30 menit

---

## P2 — Nice-to-Have untuk Demo

> Bagus kalau ada, tapi demo bisa jalan tanpa ini.

### N-01: Split `routes.py` → domain files ⬜

**Problem**: 414 lines, 7 routers dalam 1 file (God Module).
**Tasks**:
- `commodity_routes.py` — /api/commodities + /api/rca + /api/prices
- `het_routes.py` — /api/het
- `cuaca_routes.py` — /api/cuaca
- `prediction_routes.py` — /api/predictions
- `data_quality_routes.py` — /api/data-quality
**Effort**: 45 menit

### N-02: Fix SQL injection pattern di `get_predictions` ⬜

**File**: `src/api/routes.py:301-315`
**Fix**: Rewrite dengan parameterized query (`%s IS NULL OR column = %s`)
**Effort**: 10 menit

### N-03: Responsive testing (3 viewport sizes) ⬜

**Tasks**:
1. Test semua 6 halaman di 375px (mobile), 768px (tablet), 1280px (desktop)
2. Fix horizontal overflow issues
3. **Effort**: 1-2 jam

### N-04: Demo rehearsal — 4 skenario ⬜

**Scenarios** (dari `docs/demo-scenarios.md`):
1. Hari Raya Demand Spike (2026-03-13)
2. Cuaca Ekstrem (2021-01-09)
3. HET Monitoring (2026-05-01)
4. Normal Day (2025-09-15)
**Effort**: 1 jam

---

## P3 — Post-Demo (Security & Tech Debt)

> Dikerjakan setelah demo. Tidak mempengaruhi functionality.

### Security

| ID | Issue | File | Effort |
|----|-------|------|--------|
| S-02 | JWT secret fallback | `auth_routes.py:38-40` | 5 min |
| S-03 | Demo creds di login HTML | `login.html:305-306` | 2 min |
| S-04 | No server-side RBAC | `routes.py` (all endpoints) | 20 min |
| S-06 | No CORS middleware | `main.py` | 10 min |
| S-07 | No rate limiting on /login | `auth_routes.py` | 15 min |
| S-09 | SQL pattern in update_user | `auth_db.py:171-176` | 15 min |
| S-10 | No input validation UserCreate | `auth_routes.py:50-55` | 10 min |
| S-11 | No security headers | `main.py` | 30 min |
| S-17 | data-quality unauthenticated | `routes.py:338-413` | 5 min |

### Code Quality / Tech Debt

| ID | Issue | File | Effort |
|----|-------|------|--------|
| C-01 | `datetime.utcnow()` deprecated | `auth_routes.py:68` | 5 min |
| C-02 | Version mismatch pyproject vs main | `pyproject.toml` vs `main.py` | 5 min |
| C-03 | `DEBUG = True` hardcoded | `config/settings.py:57` | 5 min |
| C-04 | Custom .env parser fragile | `main.py:14-23` | 15 min |
| C-05 | `Optional` deprecated (3.10+) | Multiple files | 15 min |
| C-06 | Thread-unsafe caches | `rca_engine.py`, `commodity_data.py` | 20 min |
| C-07 | Cross-layer import src/ → etl/ | `routes.py:257` | 5 min |
| C-08 | Weather check: first not most severe | `commodity_data.py:195-203` | 15 min |
| C-09 | No logging configuration | `main.py` | 10 min |

### Test Improvements

| ID | Issue | Effort |
|----|-------|--------|
| T-01 | Edge case: `price_prev = 0` test | 10 min |
| T-02 | Edge case: empty `kota_list` test | 10 min |
| T-03 | HET boundary test (79.9% vs 80.0%) | 10 min |
| T-04 | Fix spurious `hari_raya=None` field | 5 min |
| T-05 | Fix `StokInfo.pct` default mismatch | 5 min |
| T-06 | Fix ambiguous assertion | 5 min |
| T-07 | Add `data_quality.py` test suite | 30 min |

---

## Timeline Estimate (sampai Demo June 4)

```
Minggu 1 (May 16-22):
  ├── P0: BigQuery → Supabase PostgreSQL migration (B-01 ~ B-05)  [1 hari]
  ├── F-06: config/constants.py                               [30 min]
  └── F-07: Fix demo-blocking bugs                           [30 min]

Minggu 2 (May 23-29):
  ├── F-01: Extract CSS → external stylesheet                [2-3 jam]
  ├── F-02: Update guide.html                                 [1-2 jam]
  ├── F-03: Navigation antar halaman                          [1-2 jam]
  ├── F-04: Chart.js di prediksi page                         [2-3 jam]
  └── F-05: Dashboard prediksi + RCA alert                    [2-3 jam]

Minggu 3 (May 30 - June 3):
  ├── N-01 ~ N-03: Nice-to-have (jika waktu cukup)           [2-3 jam]
  ├── N-04: Demo rehearsal                                    [1 jam]
  └── Buffer: fix bugs yang ditemukan saat rehearsal           [?]

June 4: DEMO DAY
```

**Total effort**: ~20-25 jam kerja (realistis dalam 3 minggu part-time)

---

## Dependency Graph

```
B-01 (sync Gold)
 ├── B-02 (commodity_data → PG)
 ├── B-03 (weather_data → PG)
 ├── B-04 (rca_engine → PG)
 └── B-05 (cleanup BQ client)
      │
      ├── F-05 (dashboard prediksi + alert) ← needs working data
      ├── F-04 (Chart.js prediksi) ← needs working data
      └── F-03 (navigation) ← independent

F-01 (external CSS) ← independent, bisa parallel
F-02 (guide.html) ← independent, bisa parallel
F-06 (constants.py) ← independent, quick win
F-07 (bugfixes) ← independent, quick win
```

**Critical path**: B-01 → B-02/B-03/B-04 → F-05 → N-04 (demo rehearsal)

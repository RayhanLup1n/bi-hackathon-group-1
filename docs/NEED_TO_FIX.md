# NEED_TO_FIX.md — Consolidated Testing Report

> Updated: 2026-05-24 | Branch: `feat/workflow-integration` | Demo: June 4, 2026
> Source: 5 parallel review agents (Security, FastAPI, Python, Architecture, UAT) + Kestra migration review

---

## Test Status

| Suite | Result | Count |
|-------|--------|-------|
| Unit Tests (HET + RCA + Weather) | **88/88 PASS** | 88 |
| HTML Structure Tests | **48/48 PASS** | 48 |
| E2E Tests (Playwright) | Scripts created in `tests/e2e/`, needs server | 28 |

---

## P0 - Fix Before Demo

### ~~[SEC] S-02: JWT secret fallback allows forged tokens~~ FIXED (2026-05-24)
- **File**: `src/api/auth_routes.py`, `main.py`
- **What changed**: App now raises `RuntimeError` if `JWT_SECRET` is missing and `DEBUG != true`. Dev fallback only active in debug mode. Import order in `main.py` fixed so `.envs/.env` is loaded before `auth_routes` import.
- **Current state**: Using `DEBUG=true` for dev/demo. See **[DEPLOY] JWT_SECRET production setup** below.

### ~~[SEC] S-03: Demo credentials exposed in login page HTML~~ FIXED (2026-05-24)
- **File**: `frontend/login.html`
- **What changed**: Demo hint hidden by default (`display:none`). Only visible with `?demo=1` query param in URL (for demo presentation).

### ~~[SEC] S-01: SQL injection pattern in get_predictions~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Replaced f-string `where_clause` interpolation with static SQL using `(%s IS NULL OR column = %s)` pattern. Removed `# noqa: S608`.

### ~~[PERF] BigQuery latency - no response caching~~ FIXED (2026-05-24)
- **File**: `src/data/bigquery_client.py`
- **What changed**: Added `bq_query_cached()` with thread-safe TTL cache (5-min default, max 200 entries, LRU eviction). Also added `clear_bq_cache()` for manual invalidation. Dashboard queries already use Supabase PostgreSQL (Gold layer) which is fast enough.

### [DEPLOY] JWT_SECRET production setup
- **Status**: Pending - needed before public deployment
- **Current**: `DEBUG=true` in `.envs/.env`, using dev fallback secret
- **Before production/public deploy**:
  1. Generate random secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  2. Set in `.envs/.env`:
     ```
     JWT_SECRET=<generated-secret-here>
     DEBUG=false
     ```
  3. Set same secret in Docker environment / deployment config
- **Effort**: 2 min

---

## Kestra Migration - Status

> Migrasi Airflow (4 containers) ke Kestra (2 containers) - commit `0c21f5a`
> ETL scripts rewritten: psycopg2 (Supabase raw.*) -> BigQuery batch load (FREE)

### FIXED (13 bugs + 3 new fixes resolved + 3 additional fixes 2026-05-24)
- K-01: `python -m` -> direct script execution (`python etl/scripts/xxx.py`)
- K-02: CLI args fixed (`--start-year`/`--end-year` INT, bukan `--start`/`--end`)
- K-03: `--mode master` removed (master data sudah ada di BigQuery)
- K-04: `execution.state` -> `execution.status`
- K-05: Docker socket mount dihapus (tidak perlu untuk Process runner)
- K-06: GCP credentials path comment ditambahkan untuk Windows
- K-07: Inline Python -> `etl/scripts/check_pihps_health.py`
- K-08: `dbt deps` dipisah jadi task sendiri + `|| echo` fallback
- K-09: Kestra image pinned ke `v1.3.19`
- K-11: Port 8081 dihapus
- K-13: `pyarrow` dihapus dari Dockerfile (transitive dep dari dbt-bigquery)
- NEW: Scripts rewritten untuk BigQuery (load_historical, load_weather, seed_hari_besar)
- NEW: dbt `--target-path /tmp/dbt-target` (project mount read-only)
- NEW-0523: Kestra basic-auth fixed (email format, `security` path, password requirements)
- NEW-0523: Null harga handling in `load_historical.py` (`dropna()` before BQ load)
- NEW-0523: Null required fields handling in `load_weather_historical.py` (same fix)
- NEW-0524: dbt `--log-path /tmp/dbt-logs` added (read-only filesystem fix for dbt log writes)
- NEW-0524: `dbt deps` removed invalid `--target-path` flag
- NEW-0524: loguru stderr -> stdout (`etl/config/log_config.py`) for correct Kestra UI log levels

### REMAINING (belum di-fix, low priority)
- K-10: Python version tidak di-pin (pakai default dari Kestra base image)
- K-12: `allowFailure: true` pada dbt test tanpa notifikasi
- K-06b: Windows users harus manual set `GOOGLE_APPLICATION_CREDENTIALS_DIR`
- Daily pipeline re-extracts seluruh tahun berjalan (scripts belum support single-date)
- K-14: Full pipeline belum fully tested end-to-end (dihentikan sementara, partial data loaded)
- K-15: `marts` dataset dihapus dari Terraform (dev mode). dbt auto-creates jika diperlukan, tapi belum diverifikasi di Docker environment

---

## P1 - Fix Before External Access

### ~~[SEC] S-04: No server-side RBAC on API endpoints~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Added `_require_analyst` guard for RCA/predictions, `_current_user` for viewer endpoints, `_require_admin` for data-quality. All sensitive endpoints now require authentication.

### ~~[SEC] S-06: No CORS middleware~~ FIXED (2026-05-24)
- **File**: `main.py`
- **What changed**: Added `CORSMiddleware` with explicit `allow_origins` (localhost:8000, 127.0.0.1:8000, localhost:3000). Ngrok wildcard added only in DEBUG mode.

### [SEC] S-07: No rate limiting on /login
- **File**: `src/api/auth_routes.py:124-136`
- **Problem**: No brute-force protection. Unlimited login attempts.
- **Fix**: Add `slowapi` with `5/minute` per IP limit.
- **Effort**: 15 min
- **Priority**: Post-demo (demo environment is trusted)

### ~~[BUG] Division by zero in rca_engine and persebaran_kota~~ FIXED (2026-05-24)
- **File**: `src/engine/rca_engine.py`
- **What changed**: Added guard for `price_prev == 0` (delta_pct = 0.0) and empty `kota_list` (return skip CheckResult). Edge case tests added (88 tests pass).

### ~~[BUG] Bare `except Exception` swallows errors silently~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Replaced bare `except Exception` with specific `psycopg2.errors.UndefinedTable` and `psycopg2.Error` catches.

### ~~[BUG] HET KRITIS status unreachable~~ FIXED (2026-05-24)
- **File**: `src/engine/het_monitor.py`, `config/settings.py`
- **What changed**: `HET_KRITIS_PCT = 0.95` (was 1.00). Now WASPADA=80%, KRITIS=95%, MELAMPAUI>100%. Tests updated and passing.

---

## P2 - Improve Reliability

### ~~[SEC] S-11: No security headers~~ FIXED (2026-05-24)
- **File**: `main.py`
- **What changed**: Added security headers middleware (CSP, X-Frame-Options, X-XSS-Protection, Referrer-Policy, X-Content-Type-Options). CSP allows inline scripts for Alpine.js, CDN for Chart.js.

### ~~[SEC] S-09: SQL pattern in update_user (f-string SET clause)~~ FIXED (2026-05-24)
- **File**: `src/data/auth_db.py`
- **What changed**: Rewritten with COALESCE pattern (`SET col = COALESCE(%s, col)`). No more f-string SQL.

### ~~[SEC] S-10: No input validation on UserCreate~~ FIXED (2026-05-24)
- **File**: `src/api/auth_routes.py`
- **What changed**: Added Pydantic Field validation: username (3-50 chars, alphanumeric+underscore), password (6-128 chars).

### ~~[SEC] S-17: /api/data-quality endpoints unauthenticated~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Full report requires `_require_admin`, sub-endpoints accessible to authenticated users.

### ~~[ARCH] Cross-layer ETL import in API routes~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Target provinces inlined in cuaca endpoint (4 provinces only for MVP). No more `from etl.config.constants import ...`.

### ~~[ARCH] Thread-safe caches with Lock pattern~~ FIXED (2026-05-24)
- **Files**: `src/engine/rca_engine.py`, `src/data/commodity_data.py`
- **What changed**: Added `threading.Lock()` with double-checked locking. Build new dict then swap atomically under lock.

### [ARCH] API reads raw.* instead of marts.*
- **File**: `src/data/commodity_data.py`
- **Problem**: Every request runs `ROW_NUMBER() OVER()` window functions on raw table (619K rows). `marts.mart_dashboard_harga_pangan` already exists.
- **Fix**: Query from marts instead of raw. Reduces BQ compute and latency.
- **Effort**: Medium
- **Priority**: Post-demo (caching mitigates latency for now)

### [CODE] Weather check takes first extreme, not most severe
- **File**: `src/data/commodity_data.py:195-203`
- **Problem**: Comment says "most severe wins" but code does `break` on first extreme province found (from unordered `set`).
- **Fix**: Check all provinces and pick most severe, or fix comment.
- **Effort**: 15 min

---

## Architecture - Code Organization

### Scorecard
| Aspek | Skor | Status |
|-------|------|--------|
| Directory Layout | 3/5 | Logical, tapi `config/` vs `etl/config/` membingungkan |
| Module Organization | 3/5 | 2 "god modules" (`routes.py`, `commodity_data.py`) |
| Import Graph | **2/5** | Cross-layer `src/ -> etl/`, 3x duplikasi constants |
| Naming Conventions | 4/5 | Konsisten dan deskriptif |
| Separation of Concerns | 3/5 | Engine dan data terpisah, tapi routes campur SQL |
| Config Management | **2/5** | Constants tersebar di 4 tempat |
| Test Organization | 3/5 | Engine tested, missing coverage di data layer |

### Duplikasi MVP Constants - 3 tempat!
```
etl/config/constants.py    -> MVP_COMCAT_IDS       (list)
src/data/commodity_data.py -> MVP_KOMODITAS_FILTER  (set)
src/data/data_quality.py   -> _MVP_COMCAT           (tuple)
```
**Fix**: Buat `config/constants.py` sebagai single source of truth.

### `routes.py` - 430 lines, 7 routers (God Module)
**Fix**: Split menjadi per-domain files:
- `commodity_routes.py` - /api/commodities + /api/rca + /api/prices
- `het_routes.py` - /api/het
- `cuaca_routes.py` - /api/cuaca
- `prediction_routes.py` - /api/predictions (extract SQL ke `src/data/prediction_data.py`)
- `data_quality_routes.py` - /api/data-quality

### `commodity_data.py` - 304 lines (God Module)
Does 5 different things: constants, mapping, RCA data, weather aggregation, dashboard queries.
**Fix**: Extract `price_data.py` (dashboard queries) and move weather aggregation to engine layer.

### Proposed Directory Structure
```
config/
|- settings.py              # thresholds (unchanged)
|- constants.py              # <- NEW: MVP_COMCAT_IDS, TARGET_PROVINCE_IDS, etc.

src/api/
|- commodity_routes.py       # <- RENAMED from routes.py (slimmed)
|- het_routes.py             # <- EXTRACTED
|- cuaca_routes.py           # <- EXTRACTED
|- prediction_routes.py      # <- EXTRACTED
|- data_quality_routes.py    # <- EXTRACTED
|- auth_routes.py            # (unchanged)
|- ml_routes.py              # (unchanged)

src/data/
|- prediction_data.py        # <- NEW: ML predictions SQL (from routes.py)
|- price_data.py             # <- NEW: dashboard queries (from commodity_data.py)
|- (rest unchanged)

tests/
|- unit/                     # <- RESTRUCTURED
|   |- engine/               # test_rca_engine.py, test_het_monitor.py
|   |- data/                 # test_weather_data.py, test_commodity_data.py (NEW)
|- integration/              # <- NEW: API tests
|- e2e/                      # (unchanged)
```

### Refactor Priority
| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | **`config/constants.py`** - single source of truth | 30 min | High |
| 2 | **Extract predictions SQL** ke `src/data/` | 15 min | High |
| 3 | **Split `routes.py`** -> 5 domain files | 45 min | Medium |
| 4 | **Extract `price_data.py`** | 20 min | Medium |
| 5 | Restructure `tests/` -> `unit/` + `integration/` + `e2e/` | 20 min | Low |

---

## P3 - Code Quality / Tech Debt

### ~~[CODE] `datetime.utcnow()` deprecated (Python 3.12+)~~ FIXED (2026-05-24)
- **File**: `src/api/auth_routes.py`
- **What changed**: `datetime.now(timezone.utc)` + added `iat` claim to JWT payload.

### ~~[CODE] Version mismatch pyproject.toml vs main.py~~ FIXED (2026-05-24)
- **File**: `pyproject.toml`
- **What changed**: Version synced to `0.6.0`.

### ~~[CODE] `DEBUG = True` hardcoded~~ FIXED (2026-05-24)
- **File**: `config/settings.py`
- **What changed**: `DEBUG = os.environ.get("DEBUG", "false").lower() == "true"`.

### ~~[CODE] `delete_user` returns bool but caller ignores it~~ FIXED (2026-05-24)
- **File**: `src/api/auth_routes.py`
- **What changed**: Return value checked, raises 404 if user not found.

### ~~[CODE] Wrong TimeoutError class caught~~ FIXED (2026-05-24)
- **File**: `src/data/bigquery_client.py`
- **What changed**: Now catches both `TimeoutError` and `concurrent.futures.TimeoutError`.

### ~~[CODE] Duplicate HET data loading in two endpoints~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Extracted `_build_commodity_prices()` helper shared by both HET endpoints.

### ~~[CODE] No logging configuration in main.py~~ FIXED (2026-05-24)
- **File**: `main.py`
- **What changed**: Added `logging.basicConfig()` with structured format. Level set by DEBUG env var.

### ~~[CODE] `predictions_router` defined mid-file~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: All router instantiations moved to top of file. Duplicate declarations removed.

### [CODE] Custom .env parser fragile
- **File**: `main.py:14-23`
- **Fix**: Replace with `python-dotenv` or `pydantic-settings`.
- **Priority**: Low (works fine for MVP)

### [CODE] `Optional` import deprecated for Python 3.10+
- **Files**: Multiple (commodity_data.py, weather_data.py, bigquery_client.py, etc.)
- **Fix**: Use `X | None` syntax, add `from __future__ import annotations`.
- **Priority**: Cosmetic

---

## P3 - Test Improvements

### ~~[TEST] Missing edge case tests~~ FIXED (2026-05-24)
- **What changed**: Added 3 edge case tests:
  - `test_price_prev_zero_no_division_error` - division by zero guard
  - `test_empty_kota_list_no_error` - empty kota_list guard
  - `test_het_boundary_exact_threshold` - boundary at 60% threshold

### ~~[TEST] Spurious field in test factory~~ FIXED (2026-05-24)
- **What changed**: Removed `hari_raya=None` from test factory defaults (field doesn't exist in CommodityData).

### ~~[TEST] StokInfo.pct default mismatch~~ FIXED (2026-05-24)
- **What changed**: Test factory default set to `pct=1.0` (was 0.0).

### ~~[TEST] Ambiguous assertion~~ FIXED (2026-05-24)
- **What changed**: Replaced tautological assertion with specific check: `result.checks[2].status == "clear"`.

### [TEST] No tests for data_quality.py
- **File**: `src/data/data_quality.py`
- **Fix**: Add test suite with mocked `bq_query`.
- **Priority**: Low (admin-only feature, requires BigQuery mock)

---

## UAT / HTML Issues

| Page | Issue | Severity |
|------|-------|----------|
| admin.html | Not using Alpine.js (vanilla JS) | Medium |
| index.html | Date input missing `aria-label` | Low |
| rca.html | Date input missing `aria-label` | Low |
| prediksi.html | Date input missing `aria-label` | Low |

### E2E Test Setup
```bash
uv add --dev pytest-playwright
playwright install chromium
uv run pytest tests/e2e/ --headed    # watch in browser
uv run pytest tests/e2e/             # headless
```

---

## Architecture Quick Wins (for Demo)

| # | Action | Impact | Effort | Status |
|---|--------|--------|--------|--------|
| 1 | ~~Add BQ query cache (5-min TTL)~~ | Latency 30s -> <1s | Small | DONE |
| 2 | Move ETL constants to config/ | Remove cross-layer coupling | Tiny | TODO |
| 3 | ~~Fix SQL injection pattern~~ | Security | Small | DONE |
| 4 | Add `last_updated` timestamp in API responses | Better demo UX | Small | TODO |

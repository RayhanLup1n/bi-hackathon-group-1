# NEED_TO_FIX.md — Consolidated Testing Report

> Updated: 2026-05-27 | Branch: `feat/workflow-integration` | Demo: June 4, 2026
> Source: 5 parallel review agents (Security, FastAPI, Python, Architecture, UAT) + Kestra migration review + Session 2026-05-25 review + Session 2026-05-27 review

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

### ~~[PERF] BigQuery cache key collision~~ FIXED (2026-05-24)
- **File**: `src/data/bigquery_client.py`
- **What changed**: `str(params)` on `ScalarQueryParameter` objects returned memory address, not values. Fixed with `tuple((p.name, p.value) for p in params)`.

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

### FIXED (Pipeline bug 2026-05-24)
- `sync_gold_to_postgres.py`: `KeyError: 0` in `sync_bmkg_siaga` - `db_cursor()` returns `RealDictCursor` (dict rows), but code used numeric index `row[0]`. Fixed with column names `row["tanggal"]`, `row["provinsi_id"]`, etc.

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

### ~~[SEC] S-14: Timing-safe login~~ FIXED (2026-05-24)
- **File**: `src/api/auth_routes.py`
- **What changed**: Always run `verify_password` even for non-existent usernames using a dummy bcrypt hash. Prevents username enumeration via response timing.

### ~~[SEC] S-15: Generic error messages in API~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Error messages changed from `f"... failed: {e}"` to generic messages. Internal details logged via `logger.error()` instead of exposed to client.

### ~~[SEC] S-16: Hide Swagger/ReDoc in production~~ FIXED (2026-05-24)
- **File**: `main.py`
- **What changed**: `docs_url`, `redoc_url`, `openapi_url` set to `None` when `DEBUG != true`. Only accessible in debug mode.

### ~~[SEC] S-18: XSS in admin page role display~~ FIXED (2026-05-24)
- **File**: `frontend/admin.html`
- **What changed**: `u.role` escaped with `escHtml()` in both class attribute and text content.

### ~~[INFRA] ThreadedConnectionPool + timeouts~~ FIXED (2026-05-24)
- **File**: `src/data/database.py`
- **What changed**: `SimpleConnectionPool` replaced with `ThreadedConnectionPool` (thread-safe for concurrent FastAPI requests). Added `connect_timeout=5` and `statement_timeout=15000` (15s) to DSN. Pool size increased to min=2, max=20.

### ~~[INFRA] Hari besar cache 24h TTL~~ FIXED (2026-05-24)
- **File**: `src/engine/rca_engine.py`
- **What changed**: Cache now has 24h TTL using `time.monotonic()`. If DB was unreachable at startup, retry next day instead of being stuck with empty cache forever.

### ~~[INFRA] Close BigQuery client on shutdown~~ FIXED (2026-05-24)
- **File**: `main.py`
- **What changed**: `close_bq_client()` called in lifespan shutdown. Prevents resource leak.

### ~~[INFRA] Dockerfile workers~~ FIXED (2026-05-24)
- **File**: `Dockerfile`
- **What changed**: `--workers 2` added to uvicorn CMD for concurrent request handling.

### ~~[BUG] Role guard fix in RCA page~~ FIXED (2026-05-24)
- **File**: `frontend/rca.html`
- **What changed**: `if (!me.is_admin && !me.is_analyst && me.role === 'viewer')` simplified to `if (!me.is_admin && !me.is_analyst)`. Old check was fragile - depended on `me.role` string.

### ~~[BUG] Null guard on toLocaleString in prediksi page~~ FIXED (2026-05-24)
- **File**: `frontend/prediksi.html`
- **What changed**: `nextPrediction.price.toLocaleString()` wrapped with `(nextPrediction.price || 0)`. Same for `.lower` and `.upper`. Prevents crash when ML predictions have null values.

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

### ~~[BUG] Connection leak if cur.close() raises~~ FIXED (2026-05-25)
- **File**: `src/data/database.py`
- **What changed**: Nested `finally` blocks so `release_conn(conn)` always runs even if `cur.close()` raises exception.

### ~~[SEC] /api/ml/health endpoint unauthenticated~~ FIXED (2026-05-25)
- **File**: `src/api/ml_routes.py`
- **What changed**: Added `Depends(_current_user)` to `/api/ml/health` endpoint.

### ~~[SEC] /api/stok endpoints unauthenticated~~ FIXED (2026-05-25)
- **File**: `src/api/routes.py`
- **What changed**: Added `Depends(_current_user)` to both stok endpoints (placeholder).

### ~~[SEC] TOCTOU race condition on username check~~ FIXED (2026-05-25)
- **File**: `src/data/auth_db.py`
- **What changed**: Removed SELECT-then-INSERT pattern. Now uses INSERT with `psycopg2.errors.UniqueViolation` catch for atomic duplicate check.

### ~~[SEC] HTTP 401 missing WWW-Authenticate header~~ FIXED (2026-05-25)
- **File**: `src/api/auth_routes.py`
- **What changed**: Added `headers={"WWW-Authenticate": "Bearer"}` to 401 response in login endpoint (RFC 7235 compliance).

### ~~[SEC] XSS via innerHTML for me.role in admin page~~ FIXED (2026-05-25)
- **File**: `frontend/admin.html`
- **What changed**: `me.username` and `me.role` now escaped with `escHtml()` in userBadge innerHTML.

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
- **What changed**: All 4 sub-endpoints (`/coverage`, `/outliers`, `/missing`, `/duplicates`) require `_require_admin`. Error responses use generic messages.

### ~~[ARCH] Cross-layer ETL import in API routes~~ FIXED (2026-05-24)
- **File**: `src/api/routes.py`
- **What changed**: Target provinces inlined in cuaca endpoint (4 provinces only for MVP). No more `from etl.config.constants import ...`.

### ~~[ARCH] Thread-safe caches with Lock pattern~~ FIXED (2026-05-24)
- **Files**: `src/engine/rca_engine.py`, `src/data/commodity_data.py`
- **What changed**: Added `threading.Lock()` with double-checked locking. Build new dict then swap atomically under lock.

### [SEC] S-19: debug.html exposed via /static mount
- **File**: `main.py`, `frontend/debug.html`
- **Problem**: `debug.html` (DB inspector) accessible via `/static/debug.html` to anyone. No auth check.
- **Fix**: Remove from production build, or add auth guard, or move to admin-only route.
- **Effort**: 10 min
- **Priority**: Medium (exposes internal DB structure)

### [BUG] Drought detection multi-location bug
- **File**: `src/data/weather_data.py`
- **Problem**: Drought detection checks first location only, not all locations. If drought in Makassar but not Jakarta, it may be missed depending on iteration order.
- **Fix**: Check all locations and pick most severe drought signal.
- **Effort**: 15 min
- **Priority**: Medium (affects RCA accuracy for drought scenarios)

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
| Import Graph | **2/5** | Cross-layer `src/ -> etl/` FIXED, 3x duplikasi constants |
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
| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| 1 | **`config/constants.py`** - single source of truth | 30 min | High | TODO |
| 2 | **Extract predictions SQL** ke `src/data/` | 15 min | High | TODO |
| 3 | **Split `routes.py`** -> 5 domain files | 45 min | Medium | TODO |
| 4 | **Extract `price_data.py`** | 20 min | Medium | TODO |
| 5 | Restructure `tests/` -> `unit/` + `integration/` + `e2e/` | 20 min | Low | TODO |

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

### [CODE] No token revocation mechanism
- **Problem**: JWT tokens valid for 8 hours with no server-side revocation.
- **Fix**: Add token blacklist (Redis/in-memory) or reduce TTL.
- **Priority**: Post-demo

### [CODE] Default credentials (admin/admin123, analyst/analyst123)
- **Problem**: Seeded users have weak passwords.
- **Fix**: Force password change on first login, or use env vars for initial passwords.
- **Priority**: Post-demo (acceptable for demo environment)

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

### [TEST] No auth integration tests
- **Problem**: Auth endpoints (login, register, me, CRUD) have no test coverage.
- **Fix**: Add tests with mocked database for auth flow.
- **Priority**: Medium

### [TEST] No API response model tests
- **Problem**: No tests verify API response shapes match frontend expectations.
- **Fix**: Add response model validation tests.
- **Priority**: Low

---

## UAT / HTML Issues

| Page | Issue | Severity | Status |
|------|-------|----------|--------|
| admin.html | Not using Alpine.js (vanilla JS) | Medium | TODO |
| index.html | Date input missing `aria-label` | Low | TODO |
| rca.html | Date input missing `aria-label` | Low | TODO |
| prediksi.html | Date input missing `aria-label` | Low | TODO |

### E2E Test Setup
```bash
uv add --dev pytest-playwright
playwright install chromium
uv run pytest tests/e2e/ --headed    # watch in browser
uv run pytest tests/e2e/             # headless
```

---

## Frontend Updates (2026-05-25)

### ~~[UI] Hide RCA from navigation~~ DONE (2026-05-25)
- **Files**: `index.html`, `admin.html`, `prediksi.html`, `guide.html`
- **What changed**: RCA nav links removed from all pages. Page still accessible via direct URL `/rca`. Route kept in `main.py` for backward compatibility.

### ~~[UI] Guide page rewrite - FTA + Bowtie~~ DONE (2026-05-25)
- **File**: `frontend/guide.html`
- **What changed**: Complete content rewrite from old 4-step RCA methodology to FTA + Bowtie:
  - Section 1: Platform overview (R.A.D.A.R Pangan)
  - Section 2: FTA - 6 threats (2 demand + 4 supply) with OR gate
  - Section 3: Bowtie - prevention + mitigation barriers per threat
  - Section 4: AND-Gate compound conditions with escalation levels
  - Section 5: Severity levels (L0-L4) - unchanged from engine
  - Section 6: Data sources and references

### ~~[UI] FTA + Bowtie integration in Dashboard and RCA~~ DONE (2026-05-27)
- **Files**: `frontend/index.html`, `frontend/rca.html`
- **What changed**: Added FTA Threats grid (6 cards) and Bowtie visualization (Prevention → Hazard → Mitigation) to both Dashboard and RCA page. Shows after running RCA analysis. Uses dashboard CSS classes for font/style consistency.

### ~~[BUG] Weather always showing Makassar~~ FIXED (2026-05-27)
- **File**: `src/data/commodity_data.py`
- **What changed**: Province IDs now sorted (was unordered set). Combined summary shows all provinces instead of just first. Still breaks on first extreme found (see Post-Demo #6).

### ~~[BUG] ML Docker container crash (libgomp.so.1)~~ FIXED (2026-05-27)
- **File**: `ml/Dockerfile`
- **What changed**: Added `libgomp1` to apt-get install. LightGBM requires GNU OpenMP runtime.

---

## Architecture Quick Wins (for Demo)

| # | Action | Impact | Effort | Status |
|---|--------|--------|--------|--------|
| 1 | ~~Add BQ query cache (5-min TTL)~~ | Latency 30s -> <1s | Small | DONE |
| 2 | Move ETL constants to config/ | Remove cross-layer coupling | Tiny | TODO |
| 3 | ~~Fix SQL injection pattern~~ | Security | Small | DONE |
| 4 | Add `last_updated` timestamp in API responses | Better demo UX | Small | TODO |
| 5 | ~~Fix BQ cache key collision~~ | Correct caching | Small | DONE |
| 6 | ~~ThreadedConnectionPool + timeouts~~ | Concurrent safety | Small | DONE |
| 7 | ~~Hide Swagger/ReDoc in production~~ | Security | Tiny | DONE |

---

## Post-Demo Backlog

Items below are tracked but intentionally deferred past the June 4 demo.

| # | Item | Category | Effort |
|---|------|----------|--------|
| 1 | Rate limiting on /login (`slowapi`) | Security | 15 min |
| 2 | Token revocation mechanism | Security | Medium |
| 3 | Force password change for default credentials | Security | 30 min |
| 4 | `debug.html` access control | Security | 10 min |
| 5 | Drought multi-location detection fix | Bug | 15 min |
| 6 | Weather "most severe" vs "first found" fix | Bug | 15 min — PARTIALLY FIXED (2026-05-27) — sorted province order + combined summary, but still breaks on first extreme found |
| 7 | Query marts.* instead of raw.* | Performance | Medium |
| 8 | Async httpx client for ML proxy | Performance | 30 min |
| 9 | N+1 query pattern in HET endpoints | Performance | 30 min |
| 10 | Split `routes.py` into domain files | Architecture | 45 min |
| 11 | Consolidate MVP constants to `config/constants.py` | Architecture | 30 min |
| 12 | Extract `price_data.py` from commodity_data | Architecture | 20 min |
| 13 | Auth integration tests | Testing | 1 hour |
| 14 | API response model validation tests | Testing | 30 min |
| 15 | Migrate admin.html to Alpine.js | Frontend | 1 hour |
| 16 | Add `aria-label` to date inputs | Accessibility | 10 min |
| 17 | Replace custom .env parser with python-dotenv | Tech Debt | 15 min |
| 18 | `Optional` -> `X \| None` syntax migration | Tech Debt | 20 min |
| 19 | Bowtie engine: S4 (Off-Season) has no RCA mapping | Gap | 30 min |
| 20 | Bowtie engine: D2 only activates as fallback (no direct trigger) | Gap | 1 hour |

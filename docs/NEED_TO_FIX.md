# NEED_TO_FIX.md — Consolidated Testing Report

> Updated: 2026-05-22 | Branch: `feat/workflow-integration` | Demo: June 4, 2026
> Source: 5 parallel review agents (Security, FastAPI, Python, Architecture, UAT) + Kestra migration review

---

## Test Status

| Suite | Result | Count |
|-------|--------|-------|
| Unit Tests (HET + RCA + Weather) | **36/36 PASS** | 36 |
| HTML Structure Tests | **36/40 PASS** (4 known issues) | 40 |
| E2E Tests (Playwright) | Scripts created in `tests/e2e/`, needs server | 28 |

---

## P0 — Fix Before Demo

### [SEC] S-02: JWT secret fallback allows forged tokens
- **File**: `src/api/auth_routes.py:38-40`
- **Problem**: If `JWT_SECRET` env var is missing, app silently uses a known public default string. Anyone who reads the source code can forge valid admin JWTs.
- **Fix**: Raise `RuntimeError` at startup if `JWT_SECRET` is missing or too short (< 32 chars).
- **Effort**: 5 min

### [SEC] S-03: Demo credentials exposed in login page HTML
- **File**: `frontend/login.html:305-306`
- **Problem**: `admin/admin123` and `analyst/analyst123` displayed in the login page HTML. Visible to any unauthenticated visitor.
- **Fix**: Remove the demo hint entirely, or hide behind a dev-only flag.
- **Effort**: 2 min

### [SEC] S-01: SQL injection pattern in get_predictions
- **File**: `src/api/routes.py:301-315`
- **Problem**: f-string interpolation of `where_clause` into SQL. Currently safe (predicates are hardcoded strings), but the pattern is architecturally dangerous and has a `# noqa: S608` suppression hiding the smell.
- **Fix**: Rewrite with static SQL using `COALESCE(%s, column)` pattern or `(%s IS NULL OR column = %s)`.
- **Effort**: 10 min

### [PERF] BigQuery latency — no response caching
- **File**: `src/data/bigquery_client.py` (add cache), `src/data/commodity_data.py` (N+1 calls)
- **Problem**: Dashboard page load triggers 20-30 BigQuery calls (6 komoditas × 4+ calls each). Potential 30-60 second latency. `/api/het` duplicates the same calls.
- **Fix**: Add thread-safe TTL cache (5 min) in `bigquery_client.py`:
  ```python
  import threading
  from datetime import datetime, timedelta

  _cache: dict = {}
  _cache_lock = threading.Lock()

  def bq_query_cached(sql, params=None, ttl_minutes=5):
      key = (sql, str(params))
      with _cache_lock:
          if key in _cache:
              result, expire_at = _cache[key]
              if datetime.now() < expire_at:
                  return result
      result = bq_query(sql, params)
      with _cache_lock:
          _cache[key] = (result, datetime.now() + timedelta(minutes=ttl_minutes))
      return result
  ```
- **Effort**: 30 min

---

## Kestra Migration - Status

> Migrasi Airflow (4 containers) ke Kestra (2 containers) - commit `0c21f5a`
> ETL scripts rewritten: psycopg2 (Supabase raw.*) -> BigQuery batch load (FREE)

### FIXED (13 bugs resolved)
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

### REMAINING (belum di-fix, low priority)
- K-10: Python version tidak di-pin (pakai default dari Kestra base image)
- K-12: `allowFailure: true` pada dbt test tanpa notifikasi
- K-06b: Windows users harus manual set `GOOGLE_APPLICATION_CREDENTIALS_DIR`
- Daily pipeline re-extracts seluruh tahun berjalan (scripts belum support single-date)

---

## P1 — Fix Before External Access

### [SEC] S-04: No server-side RBAC on API endpoints
- **File**: `src/api/routes.py` (all endpoints)
- **Problem**: `/api/rca/*`, `/api/commodity/*`, `/api/prices/*`, `/api/cuaca/*`, `/api/het/*`, `/api/predictions` have ZERO auth checks. Frontend guards are trivially bypassed with `curl`.
- **Fix**: Create `_require_analyst` guard and apply to sensitive endpoints.
- **Effort**: 20 min

### [SEC] S-06: No CORS middleware
- **File**: `main.py`
- **Problem**: No explicit CORS policy. Will break when frontend is served from different origin.
- **Fix**: Add `CORSMiddleware` with explicit `allow_origins` (not `"*"`).
- **Effort**: 10 min

### [SEC] S-07: No rate limiting on /login
- **File**: `src/api/auth_routes.py:124-136`
- **Problem**: No brute-force protection. Unlimited login attempts.
- **Fix**: Add `slowapi` with `5/minute` per IP limit.
- **Effort**: 15 min

### [BUG] Division by zero in rca_engine and persebaran_kota
- **File**: `src/engine/rca_engine.py:333` and `rca_engine.py:215`
- **Problem 1**: `price_prev == 0` → `ZeroDivisionError`
- **Problem 2**: `kota_list` empty → `ZeroDivisionError` in `_check_persebaran_kota`
- **Fix**: Guard both divisions:
  ```python
  # rca_engine.py:333
  if data.price_prev == 0:
      delta_pct = 0.0
  else:
      delta_pct = ((data.price_now - data.price_prev) / data.price_prev) * 100

  # rca_engine.py:215
  if total_kota == 0:
      return CheckResult(step=3, nama="...", status="skip",
                         detail="Tidak ada data kota tersedia")
  ```
- **Effort**: 10 min

### [BUG] Bare `except Exception` swallows errors silently
- **File**: `src/api/routes.py:326-328`
- **Problem**: `get_predictions` catches ALL exceptions and returns empty `{"predictions": [], "total": 0}`. DB connection failures, auth errors, and bugs are hidden.
- **Fix**: Catch specific exceptions (`psycopg2.ProgrammingError`), log others, let unexpected ones propagate as 500.
- **Effort**: 10 min

### [BUG] HET KRITIS status unreachable
- **File**: `src/engine/het_monitor.py:66-73`, `config/settings.py:37-38`
- **Problem**: `HET_KRITIS_PCT` and `HET_MELAMPAUI_PCT` are both `1.00`. The `> 100.0` check catches everything above 100%, and `>= 100.0` only triggers at exactly `100.0` (floating-point exact equality). KRITIS is effectively dead code.
- **Fix**: Remove `HET_MELAMPAUI_PCT` as separate constant; use `>` for MELAMPAUI and `==` (with tolerance) or `>=` for KRITIS.
- **Effort**: 10 min

---

## P2 — Improve Reliability

### [SEC] S-11: No security headers (CSP, X-Frame-Options, etc.)
- **File**: `main.py`
- **Fix**: Add `SecurityHeadersMiddleware` with CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
- **Effort**: 30 min

### [SEC] S-09: SQL pattern in update_user (f-string SET clause)
- **File**: `src/data/auth_db.py:171-176`
- **Fix**: Rewrite with fixed-column UPDATE using COALESCE, remove f-string entirely.
- **Effort**: 15 min

### [SEC] S-10: No input validation on UserCreate
- **File**: `src/api/auth_routes.py:50-55`
- **Fix**: Add `Field(min_length=3, max_length=50, pattern=...)` for username, `Field(min_length=8, max_length=128)` for password.
- **Effort**: 10 min

### [SEC] S-17: /api/data-quality endpoints unauthenticated
- **File**: `src/api/routes.py:338-413`
- **Fix**: Add `Depends(_require_admin)` to all data-quality endpoints.
- **Effort**: 5 min

### [ARCH] Cross-layer ETL import in API routes
- **File**: `src/api/routes.py:257`
- **Problem**: `from etl.config.constants import TARGET_PROVINCE_IDS, PROVINCE_NAMES`
- **Fix**: Move shared constants to `config/constants.py`.
- **Effort**: 5 min

### [ARCH] Thread-safe caches with Lock pattern
- **File**: `src/engine/rca_engine.py:116` (`_hari_besar_cache`), `src/data/commodity_data.py:38` (`KOMODITAS_MAP`)
- **Problem**: Race condition — concurrent threads can trigger duplicate BQ loads and read empty dicts during `.clear()`.
- **Fix**: Add `threading.Lock`, use double-checked locking, build new dict then swap atomically.
- **Effort**: 20 min

### [ARCH] API reads raw.* instead of marts.*
- **File**: `src/data/commodity_data.py`
- **Problem**: Every request runs `ROW_NUMBER() OVER()` window functions on raw table (619K rows). `marts.mart_dashboard_harga_pangan` already exists.
- **Fix**: Query from marts instead of raw. Reduces BQ compute and latency.
- **Effort**: Medium

### [CODE] Weather check takes first extreme, not most severe
- **File**: `src/data/commodity_data.py:195-203`
- **Problem**: Comment says "most severe wins" but code does `break` on first extreme province found (from unordered `set`).
- **Fix**: Check all provinces and pick most severe, or fix comment.
- **Effort**: 15 min

---

## Architecture — Code Organization

### Scorecard
| Aspek | Skor | Status |
|-------|------|--------|
| Directory Layout | 3/5 | Logical, tapi `config/` vs `etl/config/` membingungkan |
| Module Organization | 3/5 | 2 "god modules" (`routes.py`, `commodity_data.py`) |
| Import Graph | **2/5** | Cross-layer `src/ → etl/`, 3× duplikasi constants |
| Naming Conventions | 4/5 | Konsisten & deskriptif |
| Separation of Concerns | 3/5 | Engine & data terpisah, tapi routes campur SQL |
| Config Management | **2/5** | Constants tersebar di 4 tempat |
| Test Organization | 3/5 | Engine tested, missing coverage di data layer |

### Duplikasi MVP Constants — 3 tempat!
```
etl/config/constants.py    → MVP_COMCAT_IDS       (list)
src/data/commodity_data.py → MVP_KOMODITAS_FILTER  (set)
src/data/data_quality.py   → _MVP_COMCAT           (tuple)
```
**Fix**: Buat `config/constants.py` sebagai single source of truth.

### Cross-layer import: `src/` → `etl/`
```python
# routes.py:257
from etl.config.constants import TARGET_PROVINCE_IDS, PROVINCE_NAMES  # ← VIOLATION
```
**Fix**: Move shared constants ke `config/constants.py`.

### `routes.py` — 414 lines, 7 routers (God Module)
**Fix**: Split menjadi per-domain files:
- `commodity_routes.py` — /api/commodities + /api/rca + /api/prices
- `het_routes.py` — /api/het
- `cuaca_routes.py` — /api/cuaca
- `prediction_routes.py` — /api/predictions (extract SQL ke `src/data/prediction_data.py`)
- `data_quality_routes.py` — /api/data-quality

### `commodity_data.py` — 304 lines (God Module)
Does 5 different things: constants, mapping, RCA data, weather aggregation, dashboard queries.
**Fix**: Extract `price_data.py` (dashboard queries) and move weather aggregation to engine layer.

### Proposed Directory Structure
```
config/
├── settings.py              # thresholds (unchanged)
└── constants.py              # ← NEW: MVP_COMCAT_IDS, TARGET_PROVINCE_IDS, etc.

src/api/
├── commodity_routes.py       # ← RENAMED from routes.py (slimmed)
├── het_routes.py             # ← EXTRACTED
├── cuaca_routes.py           # ← EXTRACTED
├── prediction_routes.py      # ← EXTRACTED
├── data_quality_routes.py    # ← EXTRACTED
├── auth_routes.py            # (unchanged)
└── ml_routes.py              # (unchanged)

src/data/
├── prediction_data.py        # ← NEW: ML predictions SQL (from routes.py)
├── price_data.py             # ← NEW: dashboard queries (from commodity_data.py)
└── (rest unchanged)

tests/
├── unit/                     # ← RESTRUCTURED
│   ├── engine/               # test_rca_engine.py, test_het_monitor.py
│   └── data/                 # test_weather_data.py, test_commodity_data.py (NEW)
├── integration/              # ← NEW: API tests
└── e2e/                      # (unchanged)
```

### Refactor Priority
| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | **`config/constants.py`** — single source of truth | 30 min | High |
| 2 | **Extract predictions SQL** ke `src/data/` | 15 min | High |
| 3 | **Split `routes.py`** → 5 domain files | 45 min | Medium |
| 4 | **Extract `price_data.py`** | 20 min | Medium |
| 5 | Restructure `tests/` → `unit/` + `integration/` + `e2e/` | 20 min | Low |

---

## P3 — Code Quality / Tech Debt

### [CODE] `datetime.utcnow()` deprecated (Python 3.12+)
- **File**: `src/api/auth_routes.py:68`
- **Fix**: `datetime.now(timezone.utc)`, add `iat` claim to JWT payload.

### [CODE] Version mismatch pyproject.toml vs main.py
- **File**: `pyproject.toml:3` (0.3.0) vs `main.py:63` (0.5.0)
- **Fix**: Single source of truth — read from `pyproject.toml`.

### [CODE] `DEBUG = True` hardcoded
- **File**: `config/settings.py:57`
- **Fix**: `os.environ.get("DEBUG", "false").lower() == "true"`

### [CODE] Custom .env parser fragile
- **File**: `main.py:14-23`
- **Fix**: Replace with `python-dotenv` or `pydantic-settings`.

### [CODE] `Optional` import deprecated for Python 3.10+
- **Files**: Multiple (commodity_data.py, weather_data.py, bigquery_client.py, etc.)
- **Fix**: Use `X | None` syntax, add `from __future__ import annotations`.

### [CODE] `_valid_price()` can TypeError for non-float
- **File**: `src/data/commodity_data.py:41-43`
- **Fix**: Wrap in try/except, use `float()` + `math.isfinite()`.

### [CODE] Duplicate HET data loading in two endpoints
- **File**: `src/api/routes.py:168-176` and `188-196`
- **Fix**: Extract `_build_commodity_prices()` helper.

### [CODE] `delete_user` returns bool but caller ignores it
- **File**: `src/api/auth_routes.py:177-180`
- **Fix**: Check return value, raise 404 if user not found.

### [CODE] `update_user` silently skips empty password
- **File**: `src/data/auth_db.py:151`
- **Fix**: Use `is not None` check, raise ValueError for empty string.

### [CODE] Wrong TimeoutError class caught
- **File**: `src/data/bigquery_client.py:117-119`
- **Fix**: Catch `concurrent.futures.TimeoutError` in addition to built-in `TimeoutError`.

### [CODE] No logging configuration in main.py
- **File**: `main.py`
- **Fix**: Add `logging.basicConfig(level=logging.INFO, format=...)`.

### [CODE] `predictions_router` defined mid-file
- **File**: `src/api/routes.py:276`
- **Fix**: Move all router instantiations to top of file.

---

## P3 — Test Improvements

### [TEST] Missing edge case tests
- `price_prev = 0` (division by zero path)
- `kota_list` empty → ZeroDivisionError
- Post-hari-raya window (H+1, H+2, H+3)
- HET boundary 79.9% vs 80.0%
- Negative price values

### [TEST] Spurious field in test factory
- **File**: `tests/test_rca_engine.py:52`
- **Problem**: `hari_raya=None` field doesn't exist in CommodityData schema.
- **Fix**: Remove it.

### [TEST] StokInfo.pct default mismatch
- **File**: `tests/test_rca_engine.py:55`
- **Problem**: `StokInfo(pct=0.0)` default triggers "Stok Menipis" in severity scoring even when status="Normal".
- **Fix**: Set `pct=1.0` in test factory default.

### [TEST] Ambiguous assertion
- **File**: `tests/test_rca_engine.py:130`
- **Problem**: `assert result.diagnosis != DiagnosisType.SUPPLY or result.checks[1].status == "triggered"` is a tautology.
- **Fix**: Assert specific expected diagnosis.

### [TEST] No tests for data_quality.py
- **File**: `src/data/data_quality.py`
- **Fix**: Add test suite with mocked `bq_query`.

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

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | Add BQ query cache (5-min TTL) | Latency 30s → <1s | Small |
| 2 | Move ETL constants to config/ | Remove cross-layer coupling | Tiny |
| 3 | Fix SQL injection pattern | Security | Small |
| 4 | Add `last_updated` timestamp in API responses | Better demo UX | Small |

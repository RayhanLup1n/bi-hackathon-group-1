# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RCA RadarPangan is a **rule-based Root Cause Analysis engine** for diagnosing food commodity price anomalies in Indonesia. It's a FastAPI backend with a single-page dashboard frontend. The engine detects price anomalies and traces root causes through a sequential decision tree, producing actionable policy recommendations in Indonesian.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn main:app --reload

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_rca_engine.py::test_demand_spike_hari_raya -v
```

Access points:
- Login: `http://localhost:8000/login`
- Dashboard: `http://localhost:8000`
- Admin panel: `http://localhost:8000/admin`
- DB Debug: `http://localhost:8000/static/debug.html`
- Swagger API docs: `http://localhost:8000/docs`

## Architecture

### Entry Point (`main.py`)

FastAPI app v0.2.0. `lifespan` handler menginisialisasi tiga SQLite DB saat startup (idempoten):
- `init_db()` → `data/bmkg_weather.db`
- `init_db_stok()` → `data/stok.db`
- `init_db_auth()` → `data/auth.db`

Empat router di-mount: `router` (komoditas + RCA), `bmkg_router`, `stok_router`, `auth_router`. Frontend di-serve via `StaticFiles` di `/static`. Route eksplisit: `/` → `index.html`, `/login` → `login.html`, `/admin` → `admin.html`.

### Decision Tree Engine (`src/engine/rca_engine.py`)

`run_rca(data, today)` menjalankan 4 check secara sequential dan **return early pada trigger pertama**:

1. `_check_hari_raya()` → `DEMAND` — cek window H-14 s/d H+3 dari kalender di `config/settings.py`
2. `_check_cuaca()` → `SUPPLY` — cek `data.cuaca.ekstrem` (boolean dari BMKG DB)
3. `_check_persebaran_kota()` → `SUPPLY` — cek apakah ≥60% kota naik serempak
4. `_check_stok()` → `DISTRIBUSI` (stok Normal) atau `UNKNOWN` (stok Menipis/Kritis)

`DIAGNOSIS_TEMPLATES` di file yang sama menyimpan `title`, `description`, dan `action` per diagnosis type — semua teks hardcoded di sini. `_build_result()` merakit `RCAResult` dari template + checks + delta harga.

`RCAResult` selalu berisi tepat 4 `CheckResult` dengan status `"triggered" | "clear" | "skip"`.

### Auth Layer (`src/data/auth_db.py` + `src/api/auth_routes.py`)

SQLite di `data/auth.db`, tabel `users` (id, username, password_hash, role, created_at).

- **Password hashing**: `bcrypt` langsung (bukan passlib — tidak kompatibel dengan bcrypt ≥ 4.0)
- **JWT**: HS256 via `python-jose`, expire 8 jam. Secret di `_SECRET` — **ganti via env var di production**
- **Role**: `admin` (full access + user management), `analyst` (dashboard), `viewer` (read-only)
- **Default seed**: `admin/admin123` dan `analyst/analyst123` di-insert saat `init_db_auth()` pertama kali
- **Auth guard**: client-side — setiap halaman HTML cek token via `GET /api/auth/me`, redirect ke `/login` jika 401
- **Endpoint**: `POST /api/auth/login` (form), `GET /me`, `GET/POST/PATCH/DELETE /users` (admin only)

### Data Layer

#### Komoditas (`src/data/commodity_data.py`)
`DUMMY_COMMODITIES` — 4 komoditas: `cabai`, `bawang`, `beras`, `ayam`. Harga, delta, ML prediction, dan kota spread masih dummy.

`get_commodity_data(key, tanggal)` menggabungkan dummy price+kota dengan:
- Cuaca dari `bmkg_db.get_cuaca_komoditas()`
- Stok dari `stok_db.get_stok_komoditas()` → diolah `_derive_stok()` jadi `StokInfo`

#### BMKG Simulation DB (`src/data/bmkg_db.py`)
SQLite di `data/bmkg_weather.db`, 4 tabel: `wilayah`, `cuaca_harian`, `peringatan_cuaca`, `komoditas_wilayah`.

- **20 wilayah**: 12 produksi (3 per komoditas) + 8 kota konsumsi
- **Cuaca harian**: H-45 s/d H+7, deterministik via hash(wilayah+tanggal), 4 kelas iklim
- **10 peringatan ekstrem** terseed: Waspada/Siaga/Awas
- `get_cuaca_komoditas()`: prioritaskan peringatan aktif (Awas > Siaga > Waspada), fallback ke cuaca harian wilayah prioritas 1

#### Stok Simulation DB (`src/data/stok_db.py`)
SQLite di `data/stok.db`, tabel `stok_harian` (komoditas × kota × tanggal).

- Baseline stok per kota di `STOK_BASELINE`, variasi ±20% deterministik per hari
- H-45 s/d H+7 dari hari ini
- Threshold: `STOK_MENIPIS_THRESHOLD=0.60`, `STOK_KRITIS_THRESHOLD=0.35`
- Re-seed: hapus `data/stok.db` lalu restart server

### API Endpoints

Semua endpoint komoditas/BMKG/stok support `?sim_date=YYYY-MM-DD`.

**Auth** (prefix `/api/auth`):
- `POST /login` — login via form (username + password), kembalikan JWT + user info
- `GET /me` — data user aktif (Bearer token)
- `GET /users` — daftar semua users (admin only)
- `POST /users` — tambah user (admin only)
- `PATCH /users/{id}` — edit password/role (admin only)
- `DELETE /users/{id}` — hapus user (admin only)

**Komoditas** (prefix `/api`):
- `GET /commodities` — daftar key komoditas
- `GET /commodity/{key}` — data lengkap (harga, cuaca, kota, stok)
- `GET /rca/{key}` — jalankan RCA satu komoditas
- `GET /rca` — jalankan RCA semua komoditas sekaligus

**Stok** (prefix `/api/stok`):
- `GET /` — stok semua komoditas di semua kota
- `GET /{key}` — stok per kota untuk satu komoditas

**BMKG** (prefix `/api/bmkg`):
- `GET /wilayah` — list semua wilayah + metadata
- `GET /cuaca/{kode_wilayah}` — cuaca harian suatu wilayah (default 14 hari)
- `GET /peringatan` — peringatan aktif hari ini
- `GET /peringatan/history` — riwayat N hari terakhir (default 30)
- `GET /cuaca-all` — cuaca semua wilayah N hari (untuk debug)
- `GET /komoditas/{key}/wilayah-produksi` — daftar wilayah produksi per komoditas
- `GET /komoditas/{key}/cuaca` — tren cuaca 7 hari daerah produksi

### Data Flow

```
GET /api/rca/{key}?sim_date=YYYY-MM-DD
  → commodity_data.py: get_commodity_data(key, tanggal)
      → bmkg_db.py: get_cuaca_komoditas(key, tanggal)     # peringatan → cuaca harian
      → stok_db.py: get_stok_komoditas(key, tanggal)      # stok per kota → StokInfo
  → rca_engine.py: run_rca(data, today)                   # sequential decision tree
  → routes.py: return RCAResult                           # JSON response
```

### Models (`src/models/schemas.py`)

- `CommodityData` — input engine: harga, cuaca, kota_list, stok, threshold_kota (default 0.6)
- `CuacaInfo` — `ekstrem: bool`, `desc`, `daerah`, `detail`
- `StokInfo` — `status` (Normal/Menipis/Kritis), `kelas` (ok/warn/danger), `pct`
- `KotaInfo` — `nama`, `naik: bool`
- `RCAResult` — output: diagnosis, title, description, action, checks, price_delta_pct, is_anomaly
- `DiagnosisType` — enum: `DEMAND | SUPPLY | DISTRIBUSI | UNKNOWN`
- `CheckResult` — `step`, `nama`, `status` (triggered/clear/skip), `detail`
- `BmkgWilayah`, `BmkgCuacaHarian`, `BmkgPeringatan`, `BmkgPeringatanAktif` — BMKG response models

### Frontend

Tiga halaman HTML, no build step. Glassmorphism light-themed, shared CSS design system (CSS variables sama di semua file).

**`frontend/login.html`** — Login page. Cek token existing via `/api/auth/me` saat load; redirect ke `/` jika sudah login. Submit form ke `POST /api/auth/login` (form-encoded), simpan JWT + user info ke `localStorage`.

**`frontend/admin.html`** — User management. Guard: cek token + role admin via `/api/auth/me`; redirect ke `/` jika bukan admin. Tabel users dengan modal tambah/edit/hapus.

**`frontend/index.html`** — Dashboard RCA. Guard: redirect ke `/login` jika token tidak ada atau `/api/auth/me` kembalikan 401. `fetchJSON()` otomatis kirim `Authorization: Bearer`. Header menampilkan nama+role user, tombol 👥 Users (admin saja), tombol Keluar.

- **Panel kiri**: commodity selector, chips wilayah produksi (dari `/api/bmkg/komoditas/{key}/wilayah-produksi`), harga + delta% + ML pred, signal grid (tanggal, cuaca, kota naik, stok), simulasi date picker
- **Panel kanan**: anomaly banner, 4-step animated RCA checklist, result card (title + description + action)
- Simulation date picker mengontrol tanggal di semua fetch — ganti tanggal → re-fetch otomatis, kalau result sudah tampil → re-run RCA juga otomatis
- `runRCA()` animasi step-by-step: tiap check diaktifkan (600ms) lalu di-resolve, progress bar mengisi, result card muncul setelah selesai

`frontend/debug.html` — inspector DB: cuaca, peringatan, stok.

### Config (`config/settings.py`)

- `HARI_RAYA_WINDOW_DAYS = 14`, `HARI_RAYA_POST_WINDOW_DAYS = 3`
- `KOTA_SPREAD_THRESHOLD = 0.60`
- `STOK_MENIPIS_THRESHOLD = 0.60`, `STOK_KRITIS_THRESHOLD = 0.35`
- `HARI_RAYA_CALENDAR` — daftar tanggal hari raya (perlu diupdate tiap tahun)
- Placeholder URL: `BMKG_API_URL`, `BADAN_PANGAN_API_URL`, `PIHPS_API_URL`

### Tests (`tests/test_rca_engine.py`)

12 test cases. Semua test via `make_commodity()` factory helper. Tanggal referensi:
- `DATE_NORMAL = date(2025, 9, 15)` — tidak masuk window hari raya manapun
- `DATE_IDUL_ADHA = date(2025, 5, 28)` — masuk window Idul Adha 2025

Coverage: semua 4 diagnosis path, threshold boundary (tepat 60% dan di bawah), delta % calculation, anomaly flag, struktur output (selalu 4 checks).

### Data Flow (dengan Auth)

```
Browser → GET /login → serve login.html
Browser → POST /api/auth/login (form) → JWT token
Browser → GET / (Authorization: Bearer <token>)
         → index.html fetch /api/auth/me → valid → load dashboard
         → 401 → redirect /login
```

## Key Extension Points

- **Tambah rule baru**: buat `_check_*()` di `rca_engine.py`, sisipkan di `run_rca()`, tambah `DiagnosisType` + template ke `DIAGNOSIS_TEMPLATES`
- **Ubah threshold**: edit `config/settings.py`
- **Tambah komoditas**: tambah entry di `DUMMY_COMMODITIES` (`commodity_data.py`) + `STOK_BASELINE` (`stok_db.py`) + `KOMODITAS_WILAYAH_MAP` (`bmkg_db.py`)
- **Tambah wilayah produksi**: tambah entry di `WILAYAH_DATA` dan `KOMODITAS_WILAYAH_MAP` di `bmkg_db.py`, hapus `data/bmkg_weather.db`, restart
- **Tambah role baru**: tambah nilai di validasi `auth_routes.py` dan beri badge color di `admin.html`
- **JWT via env var (production)**: ganti `_SECRET` di `auth_routes.py` dengan `os.environ["JWT_SECRET"]`
- **Tambah user field**: tambah kolom di tabel `users` (`auth_db.py`), update schema Pydantic, update form di `admin.html`
- **Connect real price/kota/stok**: ganti dummy di `commodity_data.py` dan `stok_db.py` dengan API PIHPS/Badan Pangan/Bulog
- **Connect real weather**: ganti implementasi `get_cuaca_komoditas()` di `bmkg_db.py` dengan real BMKG API (URL placeholder di `settings.py`)
- **Rekomendasi per komoditas**: extend `DIAGNOSIS_TEMPLATES` jadi nested per komoditas, atau tambah field `action` di `DUMMY_COMMODITIES`

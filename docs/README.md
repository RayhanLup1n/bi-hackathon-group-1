# RCA RadarPangan

Root Cause Analysis engine untuk mendeteksi dan mendiagnosis anomali harga pangan Indonesia.  
Dilengkapi simulasi data BMKG (cuaca) dan Badan Pangan (stok), serta sistem autentikasi pengguna.

---

## Struktur Repo

```
rca-radarpangan/
├── main.py                      # Entrypoint FastAPI + route /login /admin
├── requirements.txt
├── config/
│   └── settings.py              # ← Threshold & kalender hari raya (edit di sini)
├── src/
│   ├── api/
│   │   ├── routes.py            # REST API: komoditas, RCA, BMKG, stok
│   │   └── auth_routes.py       # REST API: login, JWT, manajemen user
│   ├── engine/
│   │   └── rca_engine.py        # ← Rule engine decision tree (edit di sini)
│   ├── data/
│   │   ├── commodity_data.py    # ← Data source (ganti dummy → real di sini)
│   │   ├── bmkg_db.py           # Simulasi DB cuaca BMKG
│   │   ├── stok_db.py           # Simulasi DB stok Badan Pangan
│   │   └── auth_db.py           # DB autentikasi pengguna
│   └── models/
│       └── schemas.py           # Pydantic models / schema
├── frontend/
│   ├── index.html               # Dashboard RCA (requires login)
│   ├── login.html               # Halaman login
│   ├── admin.html               # Manajemen user (admin only)
│   └── debug.html               # DB inspector
├── data/
│   ├── bmkg_weather.db          # Auto-generated: data cuaca simulasi
│   ├── stok.db                  # Auto-generated: data stok simulasi
│   └── auth.db                  # Auto-generated: users & credentials
├── tests/
│   └── test_rca_engine.py       # Unit tests (12 test cases)
└── docs/
    ├── README.md
    └── session_YYYY-MM-DD.md    # Log per sesi pengembangan
```

---

## Cara Jalankan

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Jalankan server
uvicorn main:app --reload

# 3. Buka browser
# Login      : http://localhost:8000/login
# Dashboard  : http://localhost:8000
# Admin      : http://localhost:8000/admin
# API Docs   : http://localhost:8000/docs
# DB Debug   : http://localhost:8000/static/debug.html
```

### Akun Default (auto-seed saat pertama kali jalan)

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| analyst | analyst123 | analyst |

---

## Cara Jalankan Tests

```bash
pytest tests/ -v
```

---

## Sistem Autentikasi

### Alur Login
```
Browser → POST /api/auth/login (form: username + password)
       ← JWT token (8 jam)
Browser → simpan token di localStorage
Browser → setiap request kirim Authorization: Bearer <token>
```

### Role
| Role | Akses |
|------|-------|
| `admin` | Dashboard + manajemen user (tambah/edit/hapus) |
| `analyst` | Dashboard penuh |
| `viewer` | Dashboard (read-only — belum ada pembatasan UI, extensible) |

### Manajemen User (Admin Panel)
Buka `http://localhost:8000/admin` → tambah, edit password/role, atau hapus user.

---

## API Endpoints

### Komoditas & RCA (`/api`)
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/commodities` | Daftar komoditas |
| GET | `/api/commodity/{key}` | Data satu komoditas |
| GET | `/api/rca/{key}` | Jalankan RCA satu komoditas |
| GET | `/api/rca` | Jalankan RCA semua komoditas |

### Autentikasi (`/api/auth`)
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/auth/login` | Login, kembalikan JWT |
| GET | `/api/auth/me` | Data user yang login |
| GET | `/api/auth/users` | Daftar semua users *(admin)* |
| POST | `/api/auth/users` | Tambah user baru *(admin)* |
| PATCH | `/api/auth/users/{id}` | Edit password/role *(admin)* |
| DELETE | `/api/auth/users/{id}` | Hapus user *(admin)* |

### Stok (`/api/stok`)
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/stok` | Stok semua komoditas |
| GET | `/api/stok/{key}` | Stok per kota satu komoditas |

### BMKG (`/api/bmkg`)
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/bmkg/wilayah` | Daftar wilayah produksi |
| GET | `/api/bmkg/cuaca/{kode}` | Cuaca harian suatu wilayah |
| GET | `/api/bmkg/peringatan` | Peringatan aktif hari ini |
| GET | `/api/bmkg/peringatan/history` | Riwayat peringatan |

Semua endpoint support `?sim_date=YYYY-MM-DD` untuk simulasi tanggal.

---

## Cara Custom

### Tambah Komoditas Baru
Edit `src/data/commodity_data.py` → tambah entry di `DUMMY_COMMODITIES`:
```python
"telur": {
    "key": "telur",
    "name": "Telur Ayam",
    "price_now": 28000,
    "price_prev": 26000,
    "price_threshold": 10.0,
    ...
}
```
Tambah juga di `STOK_BASELINE` (`stok_db.py`) dan `KOMODITAS_WILAYAH_MAP` (`bmkg_db.py`).

### Ubah Threshold
Edit `config/settings.py`:
```python
KOTA_SPREAD_THRESHOLD = 0.50      # ubah dari 60% → 50%
STOK_MENIPIS_THRESHOLD = 0.55     # ubah threshold stok menipis
```

### Tambah Rule Baru ke Decision Tree
Edit `src/engine/rca_engine.py`:
1. Buat fungsi `_check_namabaru()`
2. Sisipkan di urutan yang tepat dalam `run_rca()`
3. Tambah `DiagnosisType` + template di `DIAGNOSIS_TEMPLATES`

### Sambung ke Data Real
- Harga & kota: ganti dummy di `commodity_data.py` dengan API PIHPS
- Stok: ganti `stok_db.py` dengan API Badan Pangan / Bulog
- Cuaca: ganti `get_cuaca_komoditas()` di `bmkg_db.py` dengan API BMKG

### Ganti Secret Key JWT (Production)
Di `src/api/auth_routes.py`, ganti:
```python
_SECRET = "radarpangan-secret-key-change-in-production"
```
Dengan environment variable:
```python
import os
_SECRET = os.environ["JWT_SECRET"]
```

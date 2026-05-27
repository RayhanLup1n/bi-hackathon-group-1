# Session Log - 2026-05-27 - Bowtie Analysis Integration

**Tanggal:** 27 Mei 2026
**Branch:** `feat/workflow-integration`
**Dikerjakan oleh:** Rayhan + Claude AI

---

## Ringkasan

Session ini mengimplementasikan Bowtie Analysis Engine — engine baru yang memetakan FTA threats ke prevention & mitigation barriers — beserta endpoint API dan integrasi visualisasinya di Dashboard dan RCA page. Dua bug (ML Docker crash dan weather always Makassar) juga diperbaiki.

---

## 1. Bug Fixes

### [BUG] ML Docker container crash (libgomp.so.1)

- **File**: `ml/Dockerfile`
- **What changed**: Added `libgomp1` to `apt-get install`. LightGBM requires GNU OpenMP runtime library (`libgomp.so.1`) yang tidak tersedia di `python:3.11-slim` base image.
- **Root cause**: `python:3.11-slim` menghapus banyak system library untuk memperkecil image size. LightGBM bergantung pada OpenMP untuk parallel computation.
- **Current state**: ML container starts successfully.

### [BUG] Weather always showing Makassar (province 26)

- **File**: `src/data/commodity_data.py`
- **What changed**: Province IDs sebelumnya menggunakan `list({...})` (Python `set`) yang non-deterministic ordering-nya — province 26 (Makassar/Sulawesi Selatan) selalu muncul pertama karena hash ordering. Fixed dengan `sorted({...})` agar urutan konsisten, dan combined summary sekarang menampilkan semua provinsi yang affected, bukan hanya yang pertama ditemukan.
- **Current state**: PARTIALLY FIXED — province order sekarang deterministic (sorted), dan summary mencakup semua provinsi. Namun code masih `break` pada extreme pertama yang ditemukan (bukan most severe). Lihat Post-Demo Backlog #6.

---

## 2. Bowtie Engine Implementation

### New Engine: `src/engine/bowtie_engine.py`

Engine baru yang mengimplementasikan Bowtie Analysis methodology untuk food security risk. Engine ini menerima hasil RCA dan secara otomatis mengaktifkan barriers yang relevan berdasarkan threats yang aktif.

**FTA Threats (6)**:
| ID | Nama | Tipe |
|----|------|------|
| D1 | Hari Raya / Seasonal Demand Surge | Demand |
| D2 | Tekanan Ekonomi | Demand |
| S1 | Cuaca Ekstrem | Supply |
| S2 | Defisit Stok | Supply |
| S3 | Ketimpangan Distribusi | Supply |
| S4 | Off-Season | Supply |

**Prevention Barriers (P1-P6)**: Linked ke specific threats, activated sebelum hazard terjadi.

**Mitigation Barriers (M1-M6)**: Linked ke specific threats, activated setelah hazard terdeteksi.

**Main function**: `run_bowtie(rca: RCAResult) -> BowtieResult` — auto-activates threats dan barriers berdasarkan RCA output.

### New API Endpoints: `src/api/routes.py`

| Endpoint | Method | Role | Fungsi |
|----------|--------|------|--------|
| `/api/bowtie/{key}` | GET | Analyst+ | Bowtie analysis untuk satu komoditas |
| `/api/bowtie` | GET | Analyst+ | Bowtie analysis untuk semua komoditas |

---

## 3. Frontend Updates

### FTA + Bowtie in Dashboard (`frontend/index.html`)

Setelah user menjalankan RCA analysis di Dashboard, sekarang muncul dua section tambahan:
1. **FTA Threats Grid** — 6 cards (D1/D2/S1/S2/S3/S4) dengan status aktif/tidak aktif
2. **Bowtie Visualization** — layout Prevention → Hazard Event → Mitigation, menampilkan barriers yang activated

Font consistency: menggunakan `var(--sans)` (Inter) dan dashboard CSS classes (`.card`, `.card-label`, `.signal-item`) — bukan inline styles.

### FTA + Bowtie in RCA Page (`frontend/rca.html`)

Visualisasi yang sama juga ditambahkan ke RCA page, muncul setelah FTA analysis selesai dijalankan.

### Admin Page Revert

Clarified bahwa `/admin` adalah User Management CRUD only. FTA + Bowtie tidak masuk ke admin page — sudah ada di Dashboard dan RCA page.

### Font Consistency Fix

Semua section Bowtie baru menggunakan CSS classes yang sudah ada di `frontend/css/style.css` (`.card`, `.card-label`, `.signal-item`) dan CSS variable `var(--sans)`. Tidak ada inline styles baru yang ditambahkan.

---

## 4. Infrastructure Notes

**Diskusi deployment** — tidak ada code change:
- Evaluate VM (Oracle Cloud) vs PaaS (Railway, Render) untuk demo deployment
- Oracle Cloud Free Tier registration gagal (requires credit card)
- Decision: gunakan Railway atau Render untuk demo (simpler, no credit card)
- Tidak ada perubahan di `docker-compose.yml` atau infra config

---

## 5. Files Changed

| File | What Changed |
|------|-------------|
| `ml/Dockerfile` | Added `libgomp1` to apt-get install |
| `src/data/commodity_data.py` | `list({...})` → `sorted({...})`, combined summary all provinces |
| `src/engine/bowtie_engine.py` | **NEW** — Bowtie Analysis Engine (6 threats, 12 barriers) |
| `src/api/routes.py` | Added `/api/bowtie/{key}` and `/api/bowtie` endpoints |
| `frontend/index.html` | Added FTA Threats grid + Bowtie visualization after RCA |
| `frontend/rca.html` | Added FTA Threats grid + Bowtie visualization after analysis |
| `CLAUDE.md` | Updated Engine Logic list + Frontend table |
| `docs/NEED_TO_FIX.md` | Added Bowtie gaps to Post-Demo Backlog, updated #6 status |

---

## 6. Status

### Working
- ML Docker container starts without crash
- Weather province ordering deterministic (sorted)
- Bowtie engine correctly maps RCA output to threats and barriers
- `/api/bowtie` dan `/api/bowtie/{key}` endpoints accessible (analyst+)
- FTA Threats grid dan Bowtie visualization render di Dashboard dan RCA page
- Font/style consistent dengan existing dashboard design

### Known Gaps (Post-Demo)
- Weather still breaks on first extreme found, not most severe (see Post-Demo #6)
- Bowtie S4 (Off-Season) has no direct RCA mapping — manual trigger only (Post-Demo #19)
- Bowtie D2 (Tekanan Ekonomi) only activates as RCA fallback, no direct trigger (Post-Demo #20)

### Next Steps
- Merge PR ke `main` setelah final review
- Railway/Render deployment setup untuk demo June 4
- Koordinasi dengan ML teammate untuk inference server integration

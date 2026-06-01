# Session Log - 2026-06-01 - RCA → FTA/Analysis Rename & Dashboard Polish

**Tanggal:** 1 Juni 2026
**Branch:** `feat/workflow-integration`
**Dikerjakan oleh:** Rayhan + Claude AI
**Commit:** `183f22b` → PR #10

---

## Ringkasan

Session ini merestrukturisasi UI dari "RCA" menjadi "FTA & Bowtie Analysis" berdasarkan feedback dari tim. RCA engine tetap berjalan di backend, tapi tampilan user-facing diganti sepenuhnya ke FTA/Analisis. Dashboard dipoles agar FTA + Bowtie tampil otomatis saat halaman dibuka.

---

## Konteks

- App sudah berhasil di-deploy ke **Railway** (app service only)
- ML service kena **OOM** di Railway free tier — tidak perlu di-adjust
- ETL (Kestra) tidak di-deploy karena tidak diperlukan untuk demo
- Feedback dari tim: **RCA secara tampilan tidak perlu ditampilkan**, tapi logic tetap dipakai. Yang ditampilkan hanya **FTA + Bowtie Analysis**
- Target demo: **4 Juni 2026**

---

## Perubahan

### 1. Rename Route & API

| Sebelum | Sesudah | File |
|---------|---------|------|
| Page `/rca` | `/analysis` | `main.py` |
| API `/api/rca/{key}` | `/api/analysis/{key}` | `src/api/routes.py` |
| API `/api/rca` | `/api/analysis` | `src/api/routes.py` |
| Tag `RCA & Harga` | `FTA & Harga` | `src/api/routes.py` |

**Backend engine tidak berubah** — `rca_engine.py` dan `bowtie_engine.py` tetap utuh.

### 2. Dashboard (`frontend/index.html`)

- **Hapus RCA Checklist** — panel 4-step animated sequential reveal dihapus sepenuhnya
- **Hapus CSS** — `.rca-panel`, `.rca-header`, `.check-list`, `.check-item`, `.check-num`, `.check-badge`, `.progress-bar`, `@keyframes spin-check` (net -200+ lines)
- **Hapus JS** — `resetChecks()`, `checks[]` array, `_delay()`, animated reveal loop, `rcaProgress`, `rcaBadge`
- **Relabel** — "Jalankan RCA" → "Jalankan Analisis", "Diagnosis RCA" → "Diagnosis FTA", semua comment
- **Fix card styling** — FTA Threats + Bowtie card sekarang pakai default `.card` padding (konsisten dengan card lain)
- **Auto-load FTA + Bowtie** — `selectCommodity()` sekarang otomatis panggil `runRCA()` sehingga FTA + Bowtie langsung tampil saat commodity dipilih (tidak perlu klik manual)

### 3. Analysis Page (`frontend/rca.html`)

- **Hapus FTA Checklist** — section 6-step animated checks dihapus
- **Hapus CSS** — `.rca-section`, `.rca-header`, `.rca-list`, `.rca-item`, `.rca-step-*`, `.step-pending/active/pass/fail`, `@keyframes pulse`
- **Hapus JS** — `animatedChecks[]`, animated reveal loop, `_sleep()`
- **Update nav** — href `/rca` → `/analysis`
- **Update fetch** — `/api/rca/` → `/api/analysis/`
- **Yang tetap**: Status cards, Detail Root Cause, Context (Cuaca + Hari Besar), FTA Threats, Bowtie visualization

### 4. Admin Page (`frontend/admin.html`)

- "Akses RCA + analisis detail" → "Akses FTA + analisis detail" (2 occurrences)

### 5. Guide Page (`frontend/guide.html`)

- Sudah menggunakan "FTA" dari sebelumnya — tidak perlu perubahan

### 6. Tests

| File | Perubahan |
|------|-----------|
| `test_html_structure.py` | `TestRCAPageStructure` → `TestFTAPageStructure` |
| `test_navigation.py` | URL `/rca` → `/analysis`, rename `test_nav_rca_link_works` → `test_nav_analysis_link_works` |
| `test_rbac.py` | URL `/rca` → `/analysis`, rename `test_analyst_can_access_rca` → `test_analyst_can_access_analysis` |
| `test_rca_page.py` | Full rewrite — semua URL dan docstring diupdate |

### 7. README.md

- Update fitur: RCA Engine → FTA Engine + Bowtie Analysis
- Update halaman: `/rca` → `/analysis`
- Update tech stack: scikit-learn → LightGBM + Groq LLM, tambah Railway
- Update test count: 88 → 181
- Tambah section Deployment (Railway status)
- Update struktur project: bowtie_engine.py, label FTA

---

## Yang TIDAK Diubah (Sengaja)

- `src/engine/rca_engine.py` — logic engine tetap utuh, hanya route API yang berubah
- `src/engine/bowtie_engine.py` — tidak berubah
- `src/models/schemas.py` — `RCAResult`, `CheckResult` tetap (internal naming)
- Internal JS variable names (`rcaResult`, `rcaRunning`) — internal, tidak user-facing
- CSS class names di `rca.html` yang masih tersisa — internal, tidak user-facing
- Test files untuk engine (`test_rca_engine.py`, `test_bowtie_engine.py`) — internal naming

---

## Test Results

```
============================= 181 passed in 0.78s =============================
```

Semua 181 tests tetap pass setelah perubahan.

---

## Deployment Status

| Service | Platform | Status |
|---------|----------|--------|
| App (FastAPI + Frontend) | Railway | ✅ Deployed |
| ML Inference Server | Railway | ❌ OOM (memory limit exceeded) |
| ETL (Kestra) | - | ⏸ Tidak di-deploy (tidak perlu untuk demo) |

---

## Files Changed (9 files, +109/-455)

```
frontend/admin.html              |   4 +-
frontend/index.html              | 348 ++------
frontend/rca.html                | 114 +---
main.py                          |   4 +-
src/api/routes.py                |  12 +-
tests/e2e/test_html_structure.py |   6 +-
tests/e2e/test_navigation.py     |  22 +--
tests/e2e/test_rbac.py           |  12 +-
tests/e2e/test_rca_page.py       |  42 ++---
```

# Session Log — 2026-05-09 — Auth Migration + New Pages

## Ringkasan

Sesi ini mencakup 3 milestone utama:
1. **Migrasi users table** dari `role VARCHAR` ke boolean flags (`is_admin`, `is_analyst`, `is_active`)
2. **Perencanaan 5 pages + role access matrix**
3. **Implementasi 2 halaman baru**: `/rca` (Analisis RCA) dan `/prediksi` (Prediksi ML)

---

## 1. Auth Migration: Boolean Flags

### Motivasi
- Menyimpan boolean value lebih efisien daripada VARCHAR
- Flagging lebih fleksibel (user bisa admin + analyst sekaligus)
- Query permission check lebih mudah (`WHERE is_admin = TRUE`)

### Perubahan File

| File | Perubahan |
|------|-----------|
| `src/data/auth_db.py` | Rewrite CRUD: `create_user(is_admin, is_analyst)`, `update_user(is_admin, is_analyst, is_active)`, `_compute_role()` backward compat |
| `src/api/auth_routes.py` | Pydantic models: `UserCreate(is_admin, is_analyst)`, `UserUpdate(is_admin, is_analyst, is_active)`. JWT payload includes boolean flags. `_require_admin()` uses `user["is_admin"]`. `is_active` check blocks disabled accounts. |
| `frontend/admin.html` | Neobrutalism reskin + boolean checkboxes (replace role dropdown). Status badge (Aktif/Nonaktif). |
| `etl/loaders/postgres_loader.py` | DDL updated: `is_admin BOOLEAN`, `is_analyst BOOLEAN`, `is_active BOOLEAN` |
| `etl/scripts/migrate_users_boolean_flags.py` | Migration script: ALTER TABLE, migrate role data, drop old column. Idempotent. |

### Migration Result
```
[OK] Migration complete!
  Users (2):
    #1 admin           role=admin    status=active
    #2 analyst         role=analyst  status=active
```

### Backward Compatibility
- `_compute_role(user)` derives "admin"/"analyst"/"viewer" from boolean flags
- API responses tetap include computed `role` field
- JWT payload includes both `role` (string) and `is_admin`/`is_analyst` (boolean)
- Frontend checks `user.is_admin || user.role === 'admin'` for safety

---

## 2. Page Planning + Role Access Matrix

### 5 Pages Final

| # | Page | URL | Layout | Role Min |
|---|------|-----|--------|----------|
| 1 | Login | `/login` | Single form card | Semua |
| 2 | Dashboard Monitoring | `/` | Single column, summary + HET + RCA widget | Viewer+ |
| 3 | Analisis RCA | `/rca` | Single column stacked: filter → RCA → detail → context | Analyst+ |
| 4 | Prediksi ML | `/prediksi` | Filter → summary cards → grafik → tabel prediksi | Analyst+ |
| 5 | Admin | `/admin` | Table + modal CRUD | Admin only |

### Role Access Matrix

| Page | Viewer | Analyst | Admin |
|------|--------|---------|-------|
| Login | ✅ | ✅ | ✅ |
| Dashboard | ✅ Read-only | ✅ Full | ✅ Full |
| Analisis RCA | ❌ Redirect → `/` | ✅ Full | ✅ Full |
| Prediksi ML | ❌ Redirect → `/` | ✅ Full | ✅ Full |
| Admin | ❌ Redirect → `/` | ❌ Redirect → `/` | ✅ Full |

### Sistem Konsep
- **ML = Predictor**: Memprediksi lonjakan harga berdasarkan pola historis + hari besar + cuaca
- **RCA = Validator**: Memvalidasi prediksi secara real-time ketika anomali terjadi
- Jika anomali tidak terprediksi (e.g. perang, bencana), RCA langsung memberikan alert real-time

---

## 3. Halaman Baru

### `/rca` — Analisis RCA (analyst+ only)

Layout: Single column stacked
- **Filter bar**: Komoditas (6 dropdown), Wilayah (4 provinsi), Tanggal simulasi
- **3 Summary cards**: Status (ANOMALI/NORMAL), Delta harga (%), Persebaran kota
- **4-Step RCA Checklist**: Animated sequential check (500ms active → 200ms result)
  1. Cek Hari Raya (demand window H-14 s/d H+3)
  2. Cek Cuaca Ekstrem (Open-Meteo)
  3. Cek Persebaran Kota (>60% kota naik)
  4. Cek Stok Pedagang (placeholder)
- **Detail Root Cause**: Penyebab + Rekomendasi Kebijakan (jika anomali)
- **Context cards**: Info Cuaca (Open-Meteo) + Hari Besar terdekat
- API: `GET /api/rca/{key}`, `GET /api/commodity/{key}`, `GET /api/cuaca/{prov_id}`

### `/prediksi` — Prediksi ML (analyst+ only)

Layout: Filter → Cards → Chart → Table
- **Filter bar**: Komoditas, Kota, Periode (7/14/30/90 hari)
- **3 Summary cards**: Harga Aktual, Prediksi Besok (+ CI), Model version
- **Chart placeholder**: Aktual vs Prediksi + Confidence Interval band (Chart.js integration TBD)
- **Prediction table**: Target date, komoditas, kota, prediksi, confidence range, model version
- **Empty state**: Tampil jika ML teammate belum INSERT data ke `app.ml_predictions`
- **Info banner**: Penjelasan ML = Predictor, RCA = Validator
- API: `GET /api/predictions?komoditas_id=&kota_id=&limit=`

### API Endpoint Baru

```
GET /api/predictions
  Query params: komoditas_id (optional), kota_id (optional), limit (default 30)
  Response: { predictions: [...], total: N }
  Source: app.ml_predictions table
  Returns empty if no data (ML teammate hasn't inserted yet)
```

---

## Commits Sesi Ini

```
693e2fb refactor: migrate users table from role VARCHAR to boolean flags
4f929b1 docs: update CLAUDE.md with page plan, role matrix, and checkpoint 8-9
81e344c feat: add RCA analysis and ML prediction pages with API endpoint
```

---

## Status Tests

33 tests PASS (tidak ada regresi):
- 14 HET monitor tests
- 7 weather data tests
- 12 RCA engine tests

---

## Remaining Work (Checkpoint 9)

- [ ] Add navigation links between all pages (header nav di index.html, admin.html)
- [ ] Integrasi Chart.js/Plotly di halaman prediksi (grafik aktual vs prediksi)
- [ ] End-to-end testing halaman RCA dan Prediksi ML
- [ ] Push ke remote

# Session Log — Scope Revision & Weather Integration

**Tanggal:** 9 Mei 2026
**Branch:** `feat/workflow-integration`
**Dikerjakan oleh:** Rayhan + Claude AI

---

## Ringkasan

Session ini fokus pada **revisi scope MVP** berdasarkan feedback tim, **integrasi data cuaca Open-Meteo**, dan **persiapan infrastruktur** untuk loading data provinsi baru (Banten + Sulawesi Selatan).

### Perubahan Scope dari Tim

| Aspek | Sebelumnya | Revisi Baru |
|-------|-----------|-------------|
| **Komoditas** | Cabai Merah, Bawang Merah, Beras | **Bawang Merah, Bawang Putih, Semua Cabai** (6 komoditas) |
| **Wilayah** | Jawa Barat + DKI Jakarta (10 kota) | **Jabodetabek + Jawa Barat + Sulawesi Selatan** |
| **Cuaca** | Out of scope (P2) | **IN SCOPE — Open-Meteo Historical API** |
| **Deadline** | Mid-May 2026 | **4 Juni 2026** (proposal tahap 2) |

---

## Keputusan Arsitektur

### 1. Province IDs (Verified dari raw.dim_provinsi)

| Provinsi | PIHPS ID | Status Data |
|----------|----------|-------------|
| Banten | **11** | ❌ Belum loaded (perlu run load_historical.py) |
| Jawa Barat | 12 | ✅ 312,795 rows (9 kota) |
| DKI Jakarta | 13 | ✅ 34,755 rows (1 kota: Jakarta Pusat) |
| Sulawesi Selatan | **26** | ❌ Belum loaded (perlu run load_historical.py) |

### 2. MVP Komoditas (6 item, verified dari raw.harga_pangan)

| comcat_id | Nama PIHPS | URL Key |
|-----------|-----------|---------|
| `com_11` | Bawang Merah Ukuran Sedang | `bawang_merah_ukuran_sedang` |
| `com_12` | Bawang Putih Ukuran Sedang | `bawang_putih_ukuran_sedang` |
| `com_13` | Cabai Merah Besar | `cabai_merah_besar` |
| `com_14` | Cabai Merah Keriting | `cabai_merah_keriting` |
| `com_15` | Cabai Rawit Hijau | `cabai_rawit_hijau` |
| `com_16` | Cabai Rawit Merah | `cabai_rawit_merah` |

### 3. Kota yang Sudah Ter-load (raw.dim_kota)

| Prov ID | Kota ID | Nama |
|---------|---------|------|
| 12 | 103 | Kab. Cirebon |
| 12 | 106 | Kab. Tasikmalaya |
| 12 | 27 | Kota Bandung |
| 12 | 30 | Kota Bekasi |
| 12 | 31 | Kota Bogor |
| 12 | 28 | Kota Cirebon |
| 12 | 32 | Kota Depok |
| 12 | 33 | Kota Sukabumi |
| 12 | 29 | Kota Tasikmalaya |
| 13 | 34 | Kota Jakarta Pusat |

**Catatan**: Bogor, Depok, Bekasi sudah ter-cover di Prov 12 (Jawa Barat). Tangerang ada di Prov 11 (Banten) yang belum di-load.

### 4. Database Size (Kritis!)

**Total: 363 MB / 500 MB (Supabase free tier)**

| Tabel | Size | Keterangan |
|-------|------|------------|
| `app.dashboard_harga_pangan` | 89 MB | dbt TABLE — duplikat denormalized, bisa di-optimize |
| `marts.mart_modelling_harga_pangan` | 88 MB | dbt TABLE — semua 21 komoditas |
| `marts.mart_dashboard_harga_pangan` | 83 MB | dbt TABLE — semua 21 komoditas |
| `raw.harga_pangan` | 82 MB | Data asli (54 MB data + 28 MB index) |
| `marts.mart_dashboard_ringkasan_nasional` | 7.7 MB | Agregasi nasional |
| `raw.cuaca_harian` | **3 MB** | ✅ BARU — 11,605 rows weather data |
| Lainnya | ~10 MB | dim tables, pipeline_log, app tables |

**Strategi optimasi (BELUM dijalankan)**:
- dbt models sudah di-update dengan `mvp_comcat_ids` filter
- Setelah re-run dbt, marts/app tables akan turun dari ~260 MB ke ~75 MB (hanya 6/21 komoditas)
- Ini akan memberikan ~185 MB ruang kosong untuk load Banten + Sulsel
- **Rencana jangka panjang**: Migrasi data historis ke BigQuery/GCS (post-hackathon)

### 5. Weather Integration (Open-Meteo)

**Weather locations** (configured di `etl/config/constants.py`):

```python
WEATHER_LOCATIONS = {
    11: [(-6.18, 106.63, "Tangerang")],         # Banten
    12: [(-6.92, 107.60, "Bandung"),             # Jawa Barat
         (-6.71, 108.55, "Cirebon")],
    13: [(-6.20, 106.85, "Jakarta")],            # DKI Jakarta
    26: [(-5.14, 119.43, "Makassar")],           # Sulawesi Selatan
}
```

**Weather data loaded** (11,605 rows, 2020-01-01 s/d 2026-05-09):

| Lokasi | Prov | Rows | Avg Precip | Avg Temp Max | Max Precip |
|--------|------|------|------------|-------------|------------|
| Tangerang | 11 | 2,321 | 7.8mm | 31.0°C | 101.2mm |
| Bandung | 12 | 2,321 | 5.9mm | 27.8°C | 87.9mm |
| Cirebon | 12 | 2,321 | 6.3mm | 31.8°C | **155.1mm** |
| Jakarta | 13 | 2,321 | 7.1mm | 31.5°C | 96.7mm |
| Makassar | 26 | 2,321 | 7.4mm | 29.8°C | 100.7mm |

**Extreme weather events** (berguna untuk demo RCA):

| Tanggal | Lokasi | Precip | Temp Max | Keterangan |
|---------|--------|--------|----------|------------|
| 2021-01-09 | Cirebon | **155mm** | 29.4°C | Hujan sangat lebat |
| 2020-01-01 | Cirebon | **153mm** | 26.5°C | Hujan sangat lebat |
| 2020-04-14 | Cirebon | **142mm** | 29.2°C | Hujan lebat |
| 2020-02-03 | Cirebon | **116mm** | 29.5°C | Hujan lebat |
| 2024-01-20 | Makassar | **101mm** | 26.8°C | Hujan lebat |
| 2021-08-10 | Tangerang | **101mm** | 30.5°C | Hujan lebat |

**Weather thresholds** (configured di `config/settings.py`):

| Variabel | Threshold | Artinya |
|----------|-----------|---------|
| Curah hujan | >100mm/hari | Hujan lebat / banjir |
| Kekeringan | >14 hari <1mm | Drought / kekurangan air |
| Suhu max | >38°C | Heat extreme |
| Angin max | >60 km/h | Angin merusak |

---

## Yang Dikerjakan

### Phase 1: Foundation (SELESAI)

#### 1.1 Discover Province IDs ✅
- Query `raw.dim_provinsi` → 34 provinsi
- Banten = **11** (bukan 15 seperti estimasi)
- Sulawesi Selatan = **26** (bukan 24 seperti estimasi)
- Kota-kota Jabodetabek: Bogor(31), Depok(32), Bekasi(30) sudah di Prov 12

#### 1.2 Centralize TARGET_PROVINCE_IDS ✅
- Tambah ke `etl/config/constants.py`: `[11, 12, 13, 26]`
- Tambah `MVP_COMCAT_IDS`, `WEATHER_LOCATIONS`, `PROVINCE_NAMES`
- Update 3 file ETL → import dari constants (tidak lagi hardcode)

#### 1.3 Komoditas Filter ✅
- Tambah `MVP_KOMODITAS_FILTER` di `src/data/commodity_data.py`
- `_load_komoditas_map()` sekarang hanya load 6 komoditas MVP
- API `/api/commodities` hanya return komoditas fokus

#### 1.4 dbt Komoditas Filter ✅
- Tambah `vars.mvp_comcat_ids` di `dbt_project.yml`
- Filter ditambahkan ke 3 dbt mart models + 1 app model:
  - `mart_modelling_harga_pangan.sql`
  - `mart_dashboard_harga_pangan.sql`
  - `dashboard_harga_pangan.sql` (app schema)
- **PENTING: dbt belum di-re-run** — perlu `dbt run` untuk rebuild tables

#### 1.5 Config Updates ✅
- `config/settings.py`:
  - Hapus `BMKG_API_URL`, `BADAN_PANGAN_API_URL`, `PIHPS_API_URL`
  - Tambah `OPENMETEO_API_URL`
  - Tambah weather thresholds (`WEATHER_PRECIP_EXTREME_MM`, dll)
  - Tambah HET thresholds (`HET_WASPADA_PCT`, `HET_KRITIS_PCT`, `HET_MELAMPAUI_PCT`)
  - Tambah `HET_REFERENCE` dummy prices per komoditas

### Phase 2: Weather Integration (SELESAI)

#### 2.1 Weather Schema ✅
- `raw.cuaca_harian` table DDL di `postgres_loader.py`
- Columns: tanggal, lokasi_label, provinsi_id, lat/lon, precipitation, rain, temp_max/min, wind_speed, evapotranspiration, sunshine_duration
- UNIQUE constraint: (tanggal, latitude, longitude)
- Index: (tanggal, provinsi_id)

#### 2.2 Open-Meteo Extractor ✅
- `etl/extractors/openmeteo_extractor.py`
- `extract_daily()` — single location, wide date range
- `extract_all_locations()` — all configured locations
- Free API, no authentication needed
- One API call per location (supports full date range in single request)

#### 2.3 Weather Historical Loader ✅
- `etl/scripts/load_weather_historical.py`
- UPSERT support (ON CONFLICT DO UPDATE)
- **11,605 records loaded** dalam ~15 detik (sangat cepat vs PIHPS)

#### 2.4 MCP Configuration ✅
- `.claude/.mcp.json` — Supabase MCP Server
- Perlu restart Claude Code + OAuth authentication via browser

---

## File yang Dibuat/Diubah

### Baru
| File | Keterangan |
|------|------------|
| `etl/extractors/openmeteo_extractor.py` | Open-Meteo weather API extractor |
| `etl/scripts/load_weather_historical.py` | Weather historical data loader |
| `.claude/.mcp.json` | Supabase MCP Server config |

### Diubah
| File | Perubahan |
|------|-----------|
| `etl/config/constants.py` | +TARGET_PROVINCE_IDS, +MVP_COMCAT_IDS, +WEATHER_LOCATIONS, +PROVINCE_NAMES |
| `etl/scripts/load_historical.py` | Import province IDs dari constants |
| `etl/dags/dag_data_ready_dashboard.py` | Import province IDs dari constants |
| `etl/dags/dag_data_ready_modelling.py` | Import province IDs dari constants |
| `etl/dbt_project/dbt_project.yml` | +vars.mvp_comcat_ids filter |
| `etl/dbt_project/models/marts/modelling/mart_modelling_harga_pangan.sql` | +comcat_id filter |
| `etl/dbt_project/models/marts/dashboard/mart_dashboard_harga_pangan.sql` | +comcat_id filter |
| `etl/dbt_project/models/app/dashboard_harga_pangan.sql` | +comcat_id filter |
| `etl/loaders/postgres_loader.py` | +DDL_RAW_CUACA_HARIAN, +init_schema weather table |
| `config/settings.py` | +weather thresholds, +HET thresholds, +HET_REFERENCE, +OPENMETEO_API_URL |
| `src/data/commodity_data.py` | +MVP_KOMODITAS_FILTER, filtered _load_komoditas_map() |

---

## Commits

```
6655f7c refactor: update MVP scope - new provinces, komoditas filter, weather config
e747f0f feat: add Open-Meteo weather integration (extractor + schema + loader)
51b3117 fix: add dotenv loading to weather script + fix unicode in summary
```

---

## NEXT STEPS (untuk session berikutnya)

### Urutan Prioritas

#### Step 1: Optimasi DB (WAJIB sebelum load data baru)
```bash
# Re-run dbt untuk rebuild marts/app tables dengan komoditas filter
# Ini akan turunkan DB dari ~363 MB ke ~175 MB
cd etl
uv run dbt run --profiles-dir dbt_project --project-dir dbt_project
uv run dbt test --profiles-dir dbt_project --project-dir dbt_project
```
**Perlu set env vars Supabase** sebelum run dbt, atau pastikan `.envs/.env` ter-load.

#### Step 2: Load Historical PIHPS Data (Banten + Sulsel)
```bash
# Run dari root project, bukan dari etl/
cd bi-hackathon-group-1
set PYTHONPATH=B:\project\bi-hackathon-group-1\etl
uv run python etl/scripts/load_historical.py --start-year 2020
```
**Estimasi**: 2-4 jam untuk 2 provinsi × 6 tahun.
- Banten (~4-6 kota): ~125K-190K rows (~27-51 MB)
- Sulawesi Selatan (~4-7 kota): ~105K-185K rows (~28-49 MB)

#### Step 3: Build Weather Data Layer (src/data/weather_data.py)
File baru yang perlu dibuat: `src/data/weather_data.py`

Fungsi utama:
```python
def get_weather_for_rca(
    provinsi_id: int,
    tanggal: date | None = None,
    lookback_days: int = 7,
) -> CuacaInfo:
    """
    Query raw.cuaca_harian untuk 7 hari terakhir.
    Check: hujan >100mm, kekeringan >14 hari, suhu >38°C, angin >60km/h.
    Return CuacaInfo(ekstrem=True/False, desc=..., daerah=..., detail=...).
    """
```

Lalu update `src/data/commodity_data.py`:
- Replace placeholder cuaca (line 137-143) dengan call ke `get_weather_for_rca()`
- Perlu tambah `provinsi_id` dari query harga ke CuacaInfo

Dan update `src/engine/rca_engine.py`:
- Rename "BMKG" → "Open-Meteo" di label check cuaca (line 120-133)

#### Step 4: Build HET Monitor Engine (src/engine/het_monitor.py)
File baru: `src/engine/het_monitor.py`

```python
class HETStatus(str, Enum):
    AMAN = "aman"           # harga < 80% HET
    WASPADA = "waspada"     # 80% <= harga < 100% HET
    KRITIS = "kritis"      # harga >= 100% HET
    MELAMPAUI = "melampaui" # harga > 100% HET (alias kritis, beda label)

def check_het_status(comcat_id: str, current_price: float) -> dict:
    """Compare harga vs HET_REFERENCE dari config/settings.py."""
```

API endpoints baru di `src/api/routes.py`:
- `GET /api/het/{key}` — HET status per komoditas
- `GET /api/het` — HET status semua komoditas
- `GET /api/het/summary` — ringkasan (count per status)

#### Step 5: Write Tests
- `tests/test_weather_data.py` — extreme rain, drought, normal, no data
- `tests/test_het_monitor.py` — AMAN, WASPADA, KRITIS, MELAMPAUI
- `tests/test_komoditas_filter.py` — only MVP returned, beras excluded
- Update `tests/test_rca_engine.py` — test cuaca triggered path

#### Step 6: Update Frontend + CLAUDE.md
- Frontend: HET status badge, weather info di RCA, komoditas dropdown filter
- CLAUDE.md: update scope, checkpoints, data sources

---

## Data di Database (Snapshot)

### raw.harga_pangan
- **347,550 rows** (2020-01-01 s/d 2026-05-05)
- 21 komoditas × 10 kota (Jabar + DKI)
- Banten + Sulsel belum di-load

### raw.cuaca_harian
- **11,605 rows** (2020-01-01 s/d 2026-05-09)
- 5 lokasi: Tangerang, Bandung, Cirebon, Jakarta, Makassar
- Variables: precipitation, rain, temp_max/min, wind_speed, evapotranspiration, sunshine

### raw.dim_provinsi
- 34 provinsi (semua Indonesia)

### raw.dim_kota
- 10 kota (Jabar + DKI saja, Banten + Sulsel belum)

### raw.hari_besar
- 91 rows (2024-2027)

### app.*
- users: 2 default (admin, analyst)
- het_reference: 0 (belum diisi)
- ml_predictions: 0 (menunggu ML teammate)
- komoditas_config: 0 (belum diisi)

---

## Environment & Dependencies

### Installed Extras
Session ini menjalankan `uv sync --extra etl --extra dev` yang menginstall:
- pandas, loguru, pydantic-settings, holidays, tenacity, beautifulsoup4, lxml (ETL)
- pytest, pytest-asyncio, ruff, dbt-core, dbt-postgres (dev)

### Cara Run Scripts
```bash
# Dari root project
cd B:\project\bi-hackathon-group-1

# Weather loading
set PYTHONPATH=B:\project\bi-hackathon-group-1\etl
uv run python etl/scripts/load_weather_historical.py

# PIHPS historical loading
set PYTHONPATH=B:\project\bi-hackathon-group-1\etl
uv run python etl/scripts/load_historical.py --start-year 2020

# dbt run (dari root, bukan dari etl/)
uv run dbt run --profiles-dir etl/dbt_project --project-dir etl/dbt_project

# FastAPI server
uv run uvicorn main:app --reload

# Tests
uv run pytest tests/ -v
```

### MCP Setup
- File: `.claude/.mcp.json`
- Server: `https://mcp.supabase.com/mcp`
- Setelah restart Claude Code → authenticate OAuth di browser
- MCP ini memungkinkan Claude langsung query Supabase tanpa script Python

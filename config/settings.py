# config/settings.py
# Semua parameter yang bisa di-tune tanpa ubah business logic

# ── Anomali Detection ─────────────────────────────────────────────────────
DEFAULT_PRICE_THRESHOLD_PCT = 10.0    # % kenaikan harga untuk flag anomali
HARI_RAYA_WINDOW_DAYS = 14            # H-N s/d hari H dianggap window demand spike
HARI_RAYA_POST_WINDOW_DAYS = 3        # H+N setelah hari H masih dalam window

# ── Kalender Hari Raya ────────────────────────────────────────────────────
# Format: (nama, "YYYY-MM-DD")
# Tambah tahun baru setiap tahun, atau sambungkan ke API kalender
HARI_RAYA_CALENDAR: list[tuple[str, str]] = [
    ("Idul Fitri",  "2025-03-30"),
    ("Idul Adha",   "2025-06-06"),
    ("Idul Fitri",  "2026-03-20"),
    ("Idul Adha",   "2026-05-27"),
]

# ── Rule Engine Thresholds ────────────────────────────────────────────────
KOTA_SPREAD_THRESHOLD = 0.60          # 60% kota naik = supply nasional

# ── Stok Thresholds ───────────────────────────────────────────────────────
STOK_MENIPIS_THRESHOLD = 0.60         # < 60% kapasitas normal → Menipis
STOK_KRITIS_THRESHOLD  = 0.35         # < 35% kapasitas normal → Kritis

# ── Weather Thresholds (Open-Meteo) ───────────────────────────────────────
# Thresholds for extreme weather detection in RCA engine
WEATHER_PRECIP_EXTREME_MM = 100.0     # >100mm/day = heavy rain / flooding
WEATHER_DROUGHT_DAYS = 14             # >14 consecutive days <1mm rain = drought
WEATHER_TEMP_EXTREME_C = 38.0         # >38°C = extreme heat
WEATHER_WIND_EXTREME_KMH = 60.0       # >60 km/h = damaging winds
WEATHER_LOOKBACK_DAYS = 7             # check weather in past N days for RCA

# ── HET (Harga Eceran Tertinggi) Thresholds ───────────────────────────────
# Status levels based on current price vs HET reference
HET_WASPADA_PCT = 0.80               # >= 80% of HET → WASPADA
HET_KRITIS_PCT = 1.00                # >= 100% of HET → KRITIS
HET_MELAMPAUI_PCT = 1.00             # > 100% of HET → MELAMPAUI

# Dummy HET reference prices (Rp/kg) — replace with real Bapanas data
# Sources: estimasi berdasarkan observasi pasar + berita Bapanas
HET_REFERENCE: dict[str, int] = {
    "com_11": 40_000,   # Bawang Merah — Rp 40.000/kg
    "com_12": 45_000,   # Bawang Putih — Rp 45.000/kg
    "com_13": 55_000,   # Cabai Merah Besar — Rp 55.000/kg
    "com_14": 50_000,   # Cabai Merah Keriting — Rp 50.000/kg
    "com_15": 60_000,   # Cabai Rawit Hijau — Rp 60.000/kg
    "com_16": 70_000,   # Cabai Rawit Merah — Rp 70.000/kg
}

# ── Data Sources (isi saat connect ke real API) ───────────────────────────
OPENMETEO_API_URL = "https://archive-api.open-meteo.com/v1/archive"

# ── App ───────────────────────────────────────────────────────────────────
APP_HOST = "0.0.0.0"
APP_PORT = 8000
DEBUG = True

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

# ── Data Sources (isi saat connect ke real API) ───────────────────────────
BMKG_API_URL = ""                     # https://api.bmkg.go.id/...
BADAN_PANGAN_API_URL = ""             # https://panganku.id/api/...
PIHPS_API_URL = ""                    # https://hargapangan.id/...

# ── App ───────────────────────────────────────────────────────────────────
APP_HOST = "0.0.0.0"
APP_PORT = 8000
DEBUG = True

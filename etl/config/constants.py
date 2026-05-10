"""
Konstanta untuk BI PIHPS:
- Tipe Pasar
- Kategori Komoditas
- Endpoint paths (verified dari browser DevTools)

Semua endpoint di bawah sudah dikonfirmasi dari inspeksi Network tab browser
pada https://www.bi.go.id/hargapangan/TabelHarga/PasarTradisionalDaerah

Temuan penting:
- Semua request menggunakan GET (bukan POST)
- Base path: /WebSite/TabelHarga/ sudah masuk ke PIHPS_BASE_URL,
  sehingga endpoint di ENDPOINTS cukup mulai dari /TabelHarga/
- Format tanggal: YYYY-MM-DD
- comcat_id menggunakan format "cat_N" (diisi dinamis dari GetRefCommodityAndCategory)
- Parameter "_" adalah cache-buster timestamp (opsional)
- Membutuhkan session cookie + XSRF-TOKEN header
"""
import time

# ── Tipe Pasar ────────────────────────────────────────────────────────────────
# Nilai price_type_id yang digunakan di endpoint
TIPE_PASAR = {
    "pasar_tradisional": 1,
    "pasar_modern":      2,
    "pedagang_besar":    3,
    "produsen":          4,
}

# ── Tipe Laporan ──────────────────────────────────────────────────────────────
# Parameter tipe_laporan di GetGridDataDaerah
TIPE_LAPORAN = {
    "harga_rata":  1,   # Rata-rata harga
    "harga_min":   2,   # Harga minimum
    "harga_maks":  3,   # Harga maksimum
}

# ── Kategori Komoditas (comcat_id) ────────────────────────────────────────────
# Format: "cat_N" — diisi dari hasil GetRefCommodityAndCategory
# Nilai ini perlu diverifikasi dengan memanggil endpoint GetRefCommodityAndCategory.
# Daftar di bawah adalah mapping awal berdasarkan pola umum PIHPS:
#   cat_1 = Beras & Turunannya
#   cat_2 = Bumbu & Rempah
#   dst.
# Gunakan string kosong ("") untuk ambil SEMUA kategori sekaligus.
COMCAT_ALL = ""           # kosong = semua komoditas
COMCAT_PREFIX = "cat_"   # prefix untuk semua kategori

# ── API Endpoints (relative ke base_url) ──────────────────────────────────────
# Semua endpoint menggunakan GET method.
# Verified dari browser DevTools Network tab (Fetch/XHR filter).
ENDPOINTS = {
    # ── Data Utama ───────────────────────────────────────────────────────────
    # Endpoint utama: grid data harga per daerah
    # Params: price_type_id, comcat_id, province_id, regency_id,
    #         market_id, tipe_laporan, start_date, end_date, _
    "harga_daerah":       "/TabelHarga/GetGridDataDaerah",

    # Data untuk chart/grafik (format berbeda, untuk visualisasi)
    "chart_daerah":       "/TabelHarga/GetChartDaerah",

    # ── Reference / Master Data ───────────────────────────────────────────────
    # Tipe pasar (price_type)
    # Params: filter=[["id",N]], _
    "ref_price_type":     "/TabelHarga/GetRefPriceType",

    # Daftar komoditas beserta kategorinya
    # Params: _
    "ref_komoditas":      "/TabelHarga/GetRefCommodityAndCategory",

    # Daftar provinsi
    # Params: _
    "ref_provinsi":       "/TabelHarga/GetRefProvince",

    # Daftar kabupaten/kota (opsional filter per provinsi)
    # Params: price_type_id, ref_prov_id (kosong=semua), _
    "ref_kota":           "/TabelHarga/GetRefRegency",

    # Daftar pasar (opsional filter per kab/kota)
    # Params: ref_regency_id (kosong=semua), price_type_id, _
    "ref_pasar":          "/TabelHarga/GetRefMarket",
}

# ── Halaman utama untuk inisialisasi session ──────────────────────────────────
SESSION_INIT_PATH = "/TabelHarga/PasarTradisionalDaerah"

# ── Request Headers ───────────────────────────────────────────────────────────
# Sesuai yang dikirim browser (dari curl DevTools)
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":  "en,id-ID;q=0.9,id;q=0.8,en-US;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-origin",
}

# Alias untuk backward compatibility
DEFAULT_HEADERS = BASE_HEADERS


def cache_buster() -> int:
    """Generate cache-buster timestamp (parameter '_' pada setiap request)."""
    return int(time.time() * 1000)


# ── Target Provinces ──────────────────────────────────────────────────────────
# PIHPS province IDs for extraction.
# Verified from raw.dim_provinsi via API GetRefProvince.
TARGET_PROVINCE_IDS: list[int] = [
    11,  # Banten (Tangerang — bagian dari Jabodetabek)
    12,  # Jawa Barat (Bogor, Depok, Bekasi, Bandung, dll)
    13,  # DKI Jakarta
    26,  # Sulawesi Selatan (Makassar, dll)
]

# Province ID → nama (for logging/display)
PROVINCE_NAMES: dict[int, str] = {
    11: "Banten",
    12: "Jawa Barat",
    13: "DKI Jakarta",
    26: "Sulawesi Selatan",
}


# ── MVP Komoditas ─────────────────────────────────────────────────────────────
# comcat_id dari PIHPS yang menjadi fokus MVP.
MVP_COMCAT_IDS: list[str] = [
    "com_11",  # Bawang Merah Ukuran Sedang
    "com_12",  # Bawang Putih Ukuran Sedang
    "com_13",  # Cabai Merah Besar
    "com_14",  # Cabai Merah Keriting
    "com_15",  # Cabai Rawit Hijau
    "com_16",  # Cabai Rawit Merah
]

# Human-readable mapping for display
MVP_KOMODITAS_NAMES: dict[str, str] = {
    "com_11": "Bawang Merah",
    "com_12": "Bawang Putih",
    "com_13": "Cabai Merah Besar",
    "com_14": "Cabai Merah Keriting",
    "com_15": "Cabai Rawit Hijau",
    "com_16": "Cabai Rawit Merah",
}


# ── Open-Meteo Weather Locations ──────────────────────────────────────────────
# Representative agricultural locations per province for weather data.
# Format: (latitude, longitude, label)
WEATHER_LOCATIONS: dict[int, list[tuple[float, float, str]]] = {
    11: [(-6.18, 106.63, "Tangerang")],
    12: [(-6.92, 107.60, "Bandung"), (-6.71, 108.55, "Cirebon")],
    13: [(-6.20, 106.85, "Jakarta")],
    26: [(-5.14, 119.43, "Makassar")],
}

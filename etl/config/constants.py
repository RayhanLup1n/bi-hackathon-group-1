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

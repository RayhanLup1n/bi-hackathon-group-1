"""
Data layer untuk RCA Inflasi.

Sumber data:
  - Harga, kota, stok  → DUMMY data (TODO: sambung API PIHPS / Badan Pangan / Bulog)
  - Cuaca              → bmkg_db.py (SQLite simulasi tarikan BMKG, date-aware)

Untuk ganti ke sumber real:
  - get_price_data()     → sambung ke API Badan Pangan / PIHPS
  - get_kota_spread()    → sambung ke database harga multi-kota
  - get_stok_data()      → sambung ke API Bulog / Badan Pangan
  - Cuaca sudah diarahkan ke bmkg_db; saat real tinggal ganti implementasi di sana
"""

from datetime import date
from src.models.schemas import CommodityData, CuacaInfo, KotaInfo, StokInfo
from src.data.bmkg_db import get_cuaca_komoditas
from src.data.stok_db import get_stok_komoditas
from config.settings import STOK_MENIPIS_THRESHOLD, STOK_KRITIS_THRESHOLD, COMMODITY_RELATIONS

# ──────────────────────────────────────────────
# DUMMY DATA
# Ganti isi dict ini (atau fungsi di bawah) saat connect ke data real
# ──────────────────────────────────────────────

DUMMY_COMMODITIES: dict[str, dict] = {
    "cabai": {
        "key": "cabai",
        "name": "Cabai Merah",
        "price_now": 45000,
        "price_prev": 38000,
        "price_threshold": 10.0,
        "ml_pred": 52000,
        "kota_list": [
            {"nama": "Jakarta",    "naik": True},
            {"nama": "Surabaya",   "naik": True},
            {"nama": "Bandung",    "naik": False},
            {"nama": "Semarang",   "naik": False},
            {"nama": "Yogyakarta", "naik": False},
            {"nama": "Malang",     "naik": False},
        ],
    },
    "bawang": {
        "key": "bawang",
        "name": "Bawang Merah",
        "price_now": 38000,
        "price_prev": 31000,
        "price_threshold": 10.0,
        "ml_pred": 46000,
        "kota_list": [
            {"nama": "Jakarta",    "naik": True},
            {"nama": "Surabaya",   "naik": True},
            {"nama": "Bandung",    "naik": True},
            {"nama": "Semarang",   "naik": True},
            {"nama": "Yogyakarta", "naik": True},
            {"nama": "Malang",     "naik": False},
        ],
    },
    "beras": {
        "key": "beras",
        "name": "Beras",
        "price_now": 15200,
        "price_prev": 13950,
        "price_threshold": 5.0,
        "ml_pred": 16800,
        "kota_list": [
            {"nama": "Jakarta",    "naik": True},
            {"nama": "Surabaya",   "naik": False},
            {"nama": "Bandung",    "naik": False},
            {"nama": "Semarang",   "naik": False},
            {"nama": "Yogyakarta", "naik": False},
            {"nama": "Malang",     "naik": False},
        ],
    },
    "ayam": {
        "key": "ayam",
        "name": "Daging Ayam",
        "price_now": 32000,
        "price_prev": 30500,
        "price_threshold": 10.0,
        "ml_pred": 33500,
        "kota_list": [
            {"nama": "Jakarta",    "naik": True},
            {"nama": "Surabaya",   "naik": True},
            {"nama": "Bandung",    "naik": False},
            {"nama": "Semarang",   "naik": False},
            {"nama": "Yogyakarta", "naik": False},
            {"nama": "Malang",     "naik": False},
        ],
    },
}


# ──────────────────────────────────────────────
# INTERFACE FUNCTIONS
# Ganti implementasi di sini saat punya data real
# ──────────────────────────────────────────────

def _derive_stok(stok_kota: dict[str, int], kapasitas: int) -> StokInfo:
    """Hitung status stok dari data per kota vs kapasitas normal."""
    pct = sum(stok_kota.values()) / (kapasitas * len(stok_kota))
    if pct >= STOK_MENIPIS_THRESHOLD:
        return StokInfo(status="Normal",  kelas="ok",     pct=round(pct, 3))
    elif pct >= STOK_KRITIS_THRESHOLD:
        return StokInfo(status="Menipis", kelas="warn",   pct=round(pct, 3))
    else:
        return StokInfo(status="Kritis",  kelas="danger", pct=round(pct, 3))


def get_related_deltas(key: str) -> list[dict]:
    """
    Return delta harga (%) untuk komoditas yang berkorelasi dengan key.
    Hanya pakai data harga — tidak hit DB cuaca/stok.
    Saat connect ke real data: ganti DUMMY_COMMODITIES lookup dengan query PIHPS.
    """
    result = []
    for rkey in COMMODITY_RELATIONS.get(key, []):
        raw = DUMMY_COMMODITIES.get(rkey)
        if not raw:
            continue
        delta = ((raw["price_now"] - raw["price_prev"]) / raw["price_prev"]) * 100
        result.append({
            "key":       rkey,
            "name":      raw["name"],
            "delta_pct": round(delta, 2),
            "threshold": raw["price_threshold"],
        })
    return result


def get_all_commodities() -> list[str]:
    """Return daftar key komoditas yang tersedia."""
    return list(DUMMY_COMMODITIES.keys())


def get_commodity_data(key: str, tanggal: date | None = None) -> CommodityData | None:
    """
    Ambil data lengkap satu komoditas.

    Cuaca diambil dari bmkg_db (SQLite simulasi BMKG) berdasarkan tanggal.
    Jika tanggal=None, gunakan hari ini.

    TODO (saat connect ke real data):
      price_now, price_prev  → API PIHPS / Badan Pangan
      kota_list              → query DB harga multi-kota
      stok                   → API Bulog / Badan Pangan
      Cuaca: sudah terstruktur via bmkg_db — tinggal ganti implementasi di sana
    """
    raw = DUMMY_COMMODITIES.get(key)
    if not raw:
        return None

    if tanggal is None:
        tanggal = date.today()

    cuaca = get_cuaca_komoditas(key, tanggal)

    return CommodityData(
        key=raw["key"],
        name=raw["name"],
        price_now=raw["price_now"],
        price_prev=raw["price_prev"],
        price_threshold=raw["price_threshold"],
        ml_pred=raw.get("ml_pred"),
        cuaca=cuaca,
        kota_list=[KotaInfo(**k) for k in raw["kota_list"]],
        stok=_derive_stok(*stok_raw) if (stok_raw := get_stok_komoditas(key, tanggal)) else StokInfo(status="Unknown", kelas="ok"),
    )

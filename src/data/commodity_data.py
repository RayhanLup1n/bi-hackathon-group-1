"""
Data layer: commodity data from Supabase PostgreSQL (Gold layer).

Reads real PIHPS price data from app.harga_pangan (synced from BigQuery)
and provides the same interface that routes.py expects.

Architecture:
    BigQuery -> raw.harga_pangan (Bronze, ETL only)
    Supabase -> app.harga_pangan (Gold, synced from BigQuery, served to UI)
    Supabase -> app.* (auth, HET, ML predictions)
"""
from __future__ import annotations

import math
import threading
from datetime import date, timedelta
from typing import Optional

from config.settings import DEFAULT_PRICE_THRESHOLD_PCT
from src.data.database import db_cursor
from src.data.weather_data import get_weather_for_rca
from src.models.schemas import CommodityData, CuacaInfo, StokInfo, KotaInfo


# MVP komoditas filter -- only surface these in the dashboard/API
# comcat_id values verified from app.harga_pangan
MVP_KOMODITAS_FILTER: set[str] = {
    "com_11",  # Bawang Merah Ukuran Sedang
    "com_12",  # Bawang Putih Ukuran Sedang
    "com_13",  # Cabai Merah Besar
    "com_14",  # Cabai Merah Keriting
    "com_15",  # Cabai Rawit Hijau
    "com_16",  # Cabai Rawit Merah
}

# Mapping comcat_id -> key yang user-friendly (untuk URL)
# Populated at startup from DB, filtered to MVP komoditas
# Thread-safe: lock protects clear+update, other threads see stale-but-safe data
KOMODITAS_MAP: dict[str, dict[str, str]] = {}
_komoditas_lock = threading.Lock()


def _valid_price(val: object) -> bool:
    """Check if a price value is valid (not None, not NaN, positive)."""
    if val is None:
        return False
    try:
        fval = float(val)
        return math.isfinite(fval) and fval > 0
    except (TypeError, ValueError):
        return False


def _load_komoditas_map() -> None:
    """Load komoditas mapping from Supabase PostgreSQL (called once at startup).

    Only loads MVP komoditas (bawang merah, bawang putih, all cabai types).
    Thread-safe: builds new dict then swaps atomically.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT comcat_id, komoditas_nama
            FROM app.harga_pangan
            ORDER BY comcat_id
        """)
        rows = cur.fetchall()

    # Build new dict first, then swap atomically under lock
    new_map: dict[str, dict[str, str]] = {}
    for row in rows:
        comcat_id = row["comcat_id"]

        # Filter: only include MVP komoditas
        if comcat_id not in MVP_KOMODITAS_FILTER:
            continue

        # Create URL-friendly key: "Bawang Merah Ukuran Sedang" -> "bawang_merah_ukuran_sedang"
        key = row["komoditas_nama"].lower().replace(" ", "_").replace("-", "_")
        new_map[key] = {
            "comcat_id": comcat_id,
            "name": row["komoditas_nama"],
        }

    # Atomic swap under lock
    with _komoditas_lock:
        KOMODITAS_MAP.clear()
        KOMODITAS_MAP.update(new_map)


def init_commodity_data() -> None:
    """Initialize commodity data layer. Call at app startup."""
    _load_komoditas_map()


def get_all_commodities() -> list[str]:
    """Return list of commodity keys."""
    if not KOMODITAS_MAP:
        _load_komoditas_map()
    return list(KOMODITAS_MAP.keys())


def get_commodity_data(key: str, tanggal: Optional[date] = None) -> Optional[CommodityData]:
    """
    Get commodity data for RCA engine.

    Returns CommodityData with real PIHPS data from Supabase PostgreSQL:
    - price_now: harga rata-rata hari ini (semua kota, pasar tradisional)
    - price_prev: harga rata-rata kemarin
    - kota_list: daftar kota dengan flag naik/turun
    - cuaca: real weather data dari Open-Meteo (app.cuaca_harian via Supabase)
    - stok: placeholder (tidak ada data real stok)
    """
    if not KOMODITAS_MAP:
        _load_komoditas_map()

    if key not in KOMODITAS_MAP:
        return None

    info = KOMODITAS_MAP[key]
    comcat_id = info["comcat_id"]
    target_date = tanggal or date.today()
    prev_date = target_date - timedelta(days=1)

    # PostgreSQL: use DISTINCT ON to get latest price per kota
    # Harga hari ini per kota -- cari tanggal terdekat jika hari ini belum ada
    with db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (kota_nama)
                kota_nama, provinsi_id, harga, tanggal
            FROM app.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal <= %s
            ORDER BY kota_nama, tanggal DESC
        """, (comcat_id, target_date))
        rows_today = cur.fetchall()

    # Harga kemarin per kota
    with db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (kota_nama)
                kota_nama, harga, tanggal
            FROM app.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal <= %s
            ORDER BY kota_nama, tanggal DESC
        """, (comcat_id, prev_date))
        rows_prev = cur.fetchall()

    if not rows_today:
        return None

    prices_today = [r["harga"] for r in rows_today if _valid_price(r["harga"])]
    prices_prev = [r["harga"] for r in rows_prev if _valid_price(r["harga"])]

    price_now = int(sum(prices_today) / len(prices_today)) if prices_today else 0
    price_prev = int(sum(prices_prev) / len(prices_prev)) if prices_prev else price_now

    # Build kota list with naik/turun flag
    prev_map = {r["kota_nama"]: r["harga"] for r in rows_prev if _valid_price(r["harga"])}
    kota_list = []
    for row in rows_today:
        kota_nama = row["kota_nama"]
        harga_now = row["harga"] if _valid_price(row["harga"]) else 0
        harga_prev = prev_map.get(kota_nama, harga_now)
        kota_list.append(KotaInfo(
            nama=kota_nama,
            naik=harga_now > harga_prev if harga_prev else False,
        ))

    # Price threshold for anomaly detection (default 10%)
    threshold = DEFAULT_PRICE_THRESHOLD_PCT

    # Cuaca -- check ALL provinces, pick the most severe extreme
    # Severity priority: hujan > kekeringan > suhu > angin > normal
    provinsi_ids = list({r["provinsi_id"] for r in rows_today if r.get("provinsi_id")})
    cuaca = CuacaInfo(
        ekstrem=False,
        desc="Provinsi tidak teridentifikasi",
        daerah="",
        detail="",
    )
    for prov_id in provinsi_ids:
        cuaca_check = get_weather_for_rca(prov_id, tanggal=target_date)
        if cuaca_check.ekstrem:
            # Use extreme weather (first extreme found is fine since
            # get_weather_for_rca already returns the most severe per province)
            cuaca = cuaca_check
            break
        # Keep the last non-extreme as fallback description
        if not cuaca.daerah:
            cuaca = cuaca_check

    # Stok placeholder -- tidak ada data real stok untuk MVP
    stok = StokInfo(
        status="Normal",
        kelas="ok",
        pct=1.0,
    )

    return CommodityData(
        key=key,
        name=info["name"],
        price_now=price_now,
        price_prev=price_prev,
        price_threshold=threshold,
        ml_pred=None,
        cuaca=cuaca,
        kota_list=kota_list,
        stok=stok,
    )


# --- Dashboard-specific queries -----------------------------------------------

def get_price_summary(comcat_id: str, target_date: Optional[date] = None) -> dict:
    """Get price summary for dashboard (latest prices, deltas, national avg)."""
    tgl = target_date or date.today()

    with db_cursor() as cur:
        # Find latest date with data for this komoditas
        cur.execute("""
            SELECT MAX(tanggal) AS max_tgl
            FROM app.harga_pangan
            WHERE comcat_id = %s
              AND tanggal <= %s
        """, (comcat_id, tgl))
        max_row = cur.fetchone()

        if not max_row or not max_row["max_tgl"]:
            return {}

        max_tgl = max_row["max_tgl"]

        # Get all prices for that date
        cur.execute("""
            SELECT kota_nama, harga, tanggal
            FROM app.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal = %s
            ORDER BY kota_nama
        """, (comcat_id, max_tgl))
        rows = cur.fetchall()

    if not rows:
        return {}

    prices = [r["harga"] for r in rows if _valid_price(r["harga"])]
    return {
        "tanggal": str(rows[0]["tanggal"]),
        "rata_rata": round(sum(prices) / len(prices), 2) if prices else 0,
        "harga_min": min(prices) if prices else 0,
        "harga_max": max(prices) if prices else 0,
        "jumlah_kota": len(rows),
        "per_kota": [dict(r) for r in rows],
    }


def get_price_history(
    comcat_id: str,
    n_days: int = 30,
    target_date: Optional[date] = None,
) -> list[dict]:
    """Get daily average price history for charts."""
    tgl = target_date or date.today()
    start = tgl - timedelta(days=n_days)

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                tanggal,
                ROUND(AVG(harga)::numeric, 2) as avg_harga,
                COUNT(DISTINCT kota_id) as jumlah_kota
            FROM app.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal BETWEEN %s AND %s
              AND harga > 0
            GROUP BY tanggal
            ORDER BY tanggal
        """, (comcat_id, start, tgl))
        rows = cur.fetchall()

    return [dict(r) for r in rows]

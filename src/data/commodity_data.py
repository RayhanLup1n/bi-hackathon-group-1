"""
Data layer: commodity data from Supabase PostgreSQL.

Reads real PIHPS price data from raw.harga_pangan and provides
the same interface that routes.py expects.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from src.data.database import db_cursor
from src.models.schemas import CommodityData, CuacaInfo, StokInfo, KotaInfo


# Mapping comcat_id -> key yang user-friendly (untuk URL)
# Ini hanya untuk komoditas fokus MVP — extend sesuai kebutuhan
KOMODITAS_MAP: dict[str, str] = {}  # populated at startup from DB


def _load_komoditas_map() -> None:
    """Load komoditas mapping from database (called once at startup)."""
    global KOMODITAS_MAP
    with db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT comcat_id, komoditas_nama
            FROM raw.harga_pangan
            ORDER BY comcat_id
        """)
        rows = cur.fetchall()

    KOMODITAS_MAP = {}
    for row in rows:
        # Create URL-friendly key: "Beras Kualitas Bawah I" -> "beras_kualitas_bawah_i"
        key = row["komoditas_nama"].lower().replace(" ", "_").replace("-", "_")
        KOMODITAS_MAP[key] = {
            "comcat_id": row["comcat_id"],
            "name": row["komoditas_nama"],
        }


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

    Returns CommodityData with real PIHPS data:
    - price_now: harga rata-rata hari ini (semua kota, pasar tradisional)
    - price_prev: harga rata-rata kemarin
    - kota_list: daftar kota dengan flag naik/turun
    - cuaca: placeholder (tidak ada data real BMKG)
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

    # Get harga hari ini per kota (pasar tradisional = pasar_tipe 1)
    with db_cursor() as cur:
        # Harga hari ini per kota — cari tanggal terdekat jika hari ini belum ada
        cur.execute("""
            SELECT DISTINCT ON (kota_nama)
                kota_nama,
                harga,
                tanggal
            FROM raw.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal <= %s
            ORDER BY kota_nama, tanggal DESC
        """, [comcat_id, target_date])
        rows_today = cur.fetchall()

        # Harga kemarin per kota
        cur.execute("""
            SELECT DISTINCT ON (kota_nama)
                kota_nama,
                harga,
                tanggal
            FROM raw.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal <= %s
            ORDER BY kota_nama, tanggal DESC
        """, [comcat_id, prev_date])
        rows_prev = cur.fetchall()

    if not rows_today:
        return None

    # Calculate average prices
    prices_today = [r["harga"] for r in rows_today if r["harga"]]
    prices_prev = [r["harga"] for r in rows_prev if r["harga"]]

    price_now = int(sum(prices_today) / len(prices_today)) if prices_today else 0
    price_prev = int(sum(prices_prev) / len(prices_prev)) if prices_prev else price_now

    # Build kota list with naik/turun flag
    prev_map = {r["kota_nama"]: r["harga"] for r in rows_prev}
    kota_list = []
    for row in rows_today:
        kota_nama = row["kota_nama"]
        harga_now = row["harga"] or 0
        harga_prev = prev_map.get(kota_nama, harga_now)
        kota_list.append(KotaInfo(
            nama=kota_nama,
            naik=harga_now > harga_prev if harga_prev else False,
        ))

    # Price threshold for anomaly detection (default 10%)
    from config.settings import DEFAULT_PRICE_THRESHOLD_PCT
    threshold = DEFAULT_PRICE_THRESHOLD_PCT

    # Cuaca placeholder — tidak ada data real BMKG untuk MVP
    cuaca = CuacaInfo(
        ekstrem=False,
        desc="Data cuaca tidak tersedia (MVP)",
        daerah="",
        detail="",
    )

    # Stok placeholder — tidak ada data real stok untuk MVP
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


# ─── Dashboard-specific queries ──────────────────────────────────────────────

def get_price_summary(comcat_id: str, target_date: Optional[date] = None) -> dict:
    """Get price summary for dashboard (latest prices, deltas, national avg)."""
    tgl = target_date or date.today()

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                kota_nama,
                harga,
                tanggal
            FROM raw.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal = (
                  SELECT MAX(tanggal)
                  FROM raw.harga_pangan
                  WHERE comcat_id = %s AND tanggal <= %s
              )
            ORDER BY kota_nama
        """, [comcat_id, comcat_id, tgl])
        rows = cur.fetchall()

    if not rows:
        return {}

    prices = [r["harga"] for r in rows if r["harga"]]
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
                ROUND(AVG(harga)::NUMERIC, 2) as avg_harga,
                COUNT(DISTINCT kota_id) as jumlah_kota
            FROM raw.harga_pangan
            WHERE comcat_id = %s
              AND pasar_tipe = 1
              AND tanggal BETWEEN %s AND %s
              AND harga > 0
            GROUP BY tanggal
            ORDER BY tanggal
        """, [comcat_id, start, tgl])
        rows = cur.fetchall()

    return [dict(r) for r in rows]

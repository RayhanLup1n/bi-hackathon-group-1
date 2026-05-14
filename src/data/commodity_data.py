"""
Data layer: commodity data from BigQuery (data warehouse).

Reads real PIHPS price data from BigQuery raw.harga_pangan and provides
the same interface that routes.py expects.

Architecture:
    BigQuery → raw.harga_pangan (analytics queries)
    Supabase → app.* (auth, HET, ML predictions — unchanged)
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from google.cloud.bigquery import ScalarQueryParameter

from src.data.bigquery_client import bq_query
from src.models.schemas import CommodityData, CuacaInfo, StokInfo, KotaInfo


# MVP komoditas filter — only surface these in the dashboard/API
# comcat_id values verified from raw.harga_pangan
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
KOMODITAS_MAP: dict[str, str] = {}  # populated at startup from DB


def _load_komoditas_map() -> None:
    """Load komoditas mapping from BigQuery (called once at startup).

    Only loads MVP komoditas (bawang merah, bawang putih, all cabai types).
    """
    rows = bq_query("""
        SELECT DISTINCT comcat_id, komoditas_nama
        FROM `raw.harga_pangan`
        WHERE tanggal >= '2020-01-01'
        ORDER BY comcat_id
    """)

    # Use clear + update to mutate the existing dict object in-place
    # so all modules that imported KOMODITAS_MAP see the updated data
    KOMODITAS_MAP.clear()
    for row in rows:
        comcat_id = row["comcat_id"]

        # Filter: only include MVP komoditas
        if comcat_id not in MVP_KOMODITAS_FILTER:
            continue

        # Create URL-friendly key: "Bawang Merah Ukuran Sedang" -> "bawang_merah_ukuran_sedang"
        key = row["komoditas_nama"].lower().replace(" ", "_").replace("-", "_")
        KOMODITAS_MAP[key] = {
            "comcat_id": comcat_id,
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
    - cuaca: real weather data dari Open-Meteo (raw.cuaca_harian via BigQuery)
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

    # BigQuery: no DISTINCT ON — use ROW_NUMBER() to get latest per kota
    # Harga hari ini per kota — cari tanggal terdekat jika hari ini belum ada
    rows_today = bq_query(
        """
        WITH ranked AS (
            SELECT
                kota_nama,
                provinsi_id,
                harga,
                tanggal,
                ROW_NUMBER() OVER (PARTITION BY kota_nama ORDER BY tanggal DESC) AS rn
            FROM `raw.harga_pangan`
            WHERE comcat_id = @comcat_id
              AND pasar_tipe = 1
              AND tanggal >= '2020-01-01'
              AND tanggal <= @target_date
        )
        SELECT kota_nama, provinsi_id, harga, tanggal
        FROM ranked
        WHERE rn = 1
        """,
        params=[
            ScalarQueryParameter("comcat_id", "STRING", comcat_id),
            ScalarQueryParameter("target_date", "DATE", target_date),
        ],
    )

    # Harga kemarin per kota
    rows_prev = bq_query(
        """
        WITH ranked AS (
            SELECT
                kota_nama,
                harga,
                tanggal,
                ROW_NUMBER() OVER (PARTITION BY kota_nama ORDER BY tanggal DESC) AS rn
            FROM `raw.harga_pangan`
            WHERE comcat_id = @comcat_id
              AND pasar_tipe = 1
              AND tanggal >= '2020-01-01'
              AND tanggal <= @prev_date
        )
        SELECT kota_nama, harga, tanggal
        FROM ranked
        WHERE rn = 1
        """,
        params=[
            ScalarQueryParameter("comcat_id", "STRING", comcat_id),
            ScalarQueryParameter("prev_date", "DATE", prev_date),
        ],
    )

    if not rows_today:
        return None

    # Filter out NaN/None values from prices
    def _valid_price(val) -> bool:
        return val is not None and not math.isnan(val) and val > 0

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
    from config.settings import DEFAULT_PRICE_THRESHOLD_PCT
    threshold = DEFAULT_PRICE_THRESHOLD_PCT

    # Cuaca — check ALL provinces in the data, pick the most extreme
    # This ensures we detect extreme weather regardless of which kota comes first
    from src.data.weather_data import get_weather_for_rca
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
            # Found extreme weather — use this one (most severe wins)
            cuaca = cuaca_check
            break
        # Keep the last non-extreme as fallback description
        if not cuaca.daerah:
            cuaca = cuaca_check

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


# --- Dashboard-specific queries -----------------------------------------------

def get_price_summary(comcat_id: str, target_date: Optional[date] = None) -> dict:
    """Get price summary for dashboard (latest prices, deltas, national avg)."""
    tgl = target_date or date.today()

    rows = bq_query(
        """
        WITH latest AS (
            SELECT MAX(tanggal) AS max_tgl
            FROM `raw.harga_pangan`
            WHERE comcat_id = @comcat_id
              AND tanggal >= '2020-01-01'
              AND tanggal <= @tgl
        )
        SELECT
            hp.kota_nama,
            hp.harga,
            hp.tanggal
        FROM `raw.harga_pangan` hp
        CROSS JOIN latest
        WHERE hp.comcat_id = @comcat_id
          AND hp.pasar_tipe = 1
          AND hp.tanggal >= '2020-01-01'
          AND hp.tanggal = latest.max_tgl
        ORDER BY hp.kota_nama
        """,
        params=[
            ScalarQueryParameter("comcat_id", "STRING", comcat_id),
            ScalarQueryParameter("tgl", "DATE", tgl),
        ],
    )

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

    rows = bq_query(
        """
        SELECT
            tanggal,
            ROUND(CAST(AVG(harga) AS NUMERIC), 2) as avg_harga,
            COUNT(DISTINCT kota_id) as jumlah_kota
        FROM `raw.harga_pangan`
        WHERE comcat_id = @comcat_id
          AND pasar_tipe = 1
          AND tanggal >= '2020-01-01'
          AND tanggal BETWEEN @start_date AND @end_date
          AND harga > 0
        GROUP BY tanggal
        ORDER BY tanggal
        """,
        params=[
            ScalarQueryParameter("comcat_id", "STRING", comcat_id),
            ScalarQueryParameter("start_date", "DATE", start),
            ScalarQueryParameter("end_date", "DATE", tgl),
        ],
    )

    return [dict(r) for r in rows]

"""
Stock data loader — national-level commodity stock from CSV.

Source: docs/knowledge-base/komoditas_pangan_nasional_2024-2025.csv
Data level: Nasional (agregat), per bulan.
Unit: tonnes (estimated from context).

Provides:
  - get_national_stock(commodity_name, month, year) -> int | None
  - get_stock_trend(commodity_name, month, year) -> StockInfo
"""
from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from src.domain.schemas.models import StokInfo

logger = logging.getLogger(__name__)

# Path to national stock data CSV (relative to project root)
_STOCK_CSV_PATH = Path(__file__).parent.parent.parent / "docs" / "knowledge-base" / "komoditas_pangan_nasional_2024-2025.csv"

# Mapping: CSV commodity name -> our internal comcat_id / display name
# CSV uses informal names (e.g. "Cabai Besar", "Bawang Merah ")
_CSV_NAME_TO_COMCAT: dict[str, str] = {
    "Bawang Merah": "com_11",
    "Bawang Putih": "com_12",
    "Cabai Besar": "com_13",
    "Cabai Rawit": "com_15",  # closest match — CSV doesn't separate hijau/merah
    "Daging Sapi": "",        # not MVP
    "Daging Ayam": "",        # not MVP
    "Telur Ayam": "",         # not MVP
    "Gula Pasir": "",          # not MVP
    "Beras Penggilingan": "",  # not MVP
    "Beras Pedagang": "",     # not MVP
    "Jagung": "",             # not MVP
}

# Month name (Bahasa Indonesia) -> number
_BULAN_MAP: dict[str, int] = {
    "Januari": 1, "Februari": 2, "Maret": 3, "April": 4,
    "Mei": 5, "Juni": 6, "Juli": 7, "Agustus": 8,
    "September": 9, "Oktober": 10, "November": 11, "Desember": 12,
}

# Cache: loaded stock data { (commodity_clean, year, month): stock_value }
_stock_cache: dict[tuple[str, int, int], int] = {}
_loaded: bool = False


def _load_stock_data() -> None:
    """Load stock CSV into memory cache. Called once, lazily."""
    global _loaded, _stock_cache

    if _loaded:
        return

    csv_path = _STOCK_CSV_PATH
    if not csv_path.exists():
        logger.warning(f"Stock data CSV not found at {csv_path}")
        _loaded = True
        return

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean commodity name — strip whitespace
                komoditas = row["Komoditas"].strip()
                tahun_str = row["Tahun"].strip()
                bulan_str = row["Bulan"].strip()
                stok_str = row["Stok"].strip()

                try:
                    tahun = int(tahun_str)
                    bulan = _BULAN_MAP.get(bulan_str)
                    if bulan is None:
                        continue
                    stok = int(stok_str)
                except (ValueError, KeyError):
                    continue

                _stock_cache[(komoditas, tahun, bulan)] = stok

        _loaded = True
        logger.info(f"Loaded {len(_stock_cache)} stock records from {csv_path}")
    except Exception as e:
        logger.warning(f"Failed to load stock CSV: {e}")
        _loaded = True


def get_national_stock(
    commodity_name: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[int]:
    """Get national stock for a commodity in a given month/year.

    Args:
        commodity_name: Name matching CSV (e.g. "Bawang Merah", "Cabai Besar")
        month: 1-12. Defaults to latest available month.
        year: 4-digit year. Defaults to latest available year.

    Returns:
        Stock value in tonnes, or None if not available.
    """
    _load_stock_data()

    if not _stock_cache:
        return None

    # Default to most recent available data
    if month is None or year is None:
        available = sorted(_stock_cache.keys(), key=lambda k: (k[1], k[2]), reverse=True)
        if not available:
            return None
        best = available[0]
        year = year or best[1]
        month = month or best[2]

    return _stock_cache.get((commodity_name, year, month))


def get_stock_signal(
    comcat_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> StokInfo:
    """Get stock signal for a given comcat_id.

    Compares current month stock with previous month to detect trends.
    Falls back gracefully if data is not available.

    Args:
        comcat_id: Our internal commodity ID (e.g. "com_11")
        month: Target month (1-12). Defaults to latest available.
        year: Target year. Defaults to latest available.

    Returns:
        StokInfo with status, level class, ratio, and detail description.
    """
    _load_stock_data()

    # Reverse lookup: find CSV name for this comcat_id
    csv_name = None
    for name, cid in _CSV_NAME_TO_COMCAT.items():
        if cid == comcat_id:
            csv_name = name
            break

    if csv_name is None:
        return StokInfo(
            status="Tidak tersedia",
            kelas="muted",
            pct=0.0,
        )

    current = get_national_stock(csv_name, month=month, year=year)

    # Try to find previous month for trend
    prev_month = month - 1 if month and month > 1 else 12
    prev_year = year if month and month > 1 else (year - 1 if year else None)
    previous = get_national_stock(csv_name, month=prev_month, year=prev_year) if month and year else None

    if current is None:
        return StokInfo(
            status="Data kosong",
            kelas="muted",
            pct=0.0,
        )

    # Determine status based on trend
    if previous and previous > 0:
        change_pct = (current - previous) / previous
        if change_pct < -0.15:
            status = "Menipis"
            kelas = "warn"
        elif change_pct < -0.30:
            status = "Kritis"
            kelas = "danger"
        else:
            status = "Normal"
            kelas = "ok"
    else:
        change_pct = 0.0
        status = "Normal"
        kelas = "ok"

    # Normalize pct for display — how much of max observed?
    all_stocks = [v for k, v in _stock_cache.items() if k[0] == csv_name]
    max_stock = max(all_stocks) if all_stocks else current
    pct = min(1.0, current / max_stock) if max_stock > 0 else 1.0

    return StokInfo(
        status=status,
        kelas=kelas,
        pct=round(pct, 2),
    )


def get_stock_from_comcat(comcat_id: str) -> StokInfo:
    """Convenience wrapper — get stock signal using latest available data."""
    today = date.today()
    return get_stock_signal(comcat_id, month=today.month, year=today.year)

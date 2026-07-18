"""
HET Monitor Engine — Perbandingan harga aktual vs Harga Eceran Tertinggi (HET).

Status levels:
  AMAN      — harga < 80% HET → aman, masih banyak ruang
  WASPADA   — 80% <= harga < 100% HET → mendekati batas, perlu perhatian
  KRITIS    — harga >= 100% HET → sudah mencapai batas
  MELAMPAUI — harga > 100% HET → sudah melampaui batas, perlu intervensi

Usage:
    from src.domain.engines.het_monitor import check_het_status, check_het_all

    result = check_het_status("com_11", current_price=38000)
    # → {"status": "waspada", "het": 40000, "pct": 95.0, ...}
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from config.settings import HET_KRITIS_PCT, HET_MELAMPAUI_PCT, HET_REFERENCE, HET_WASPADA_PCT


class HETStatus(str, Enum):
    """HET comparison status levels."""
    AMAN = "aman"
    WASPADA = "waspada"
    KRITIS = "kritis"
    MELAMPAUI = "melampaui"
    TIDAK_TERSEDIA = "tidak_tersedia"  # no HET reference for this komoditas


class HETResult(BaseModel):
    """Result of HET comparison for one komoditas."""
    comcat_id: str
    komoditas_nama: str
    status: HETStatus
    harga_aktual: int               # current price (Rp)
    het_harga: Optional[int] = None  # HET reference price (Rp)
    pct_of_het: Optional[float] = None  # percentage of HET (0-100+)
    selisih: Optional[int] = None   # difference (harga - het, negative = below)
    keterangan: str = ""            # human-readable description


# Status badge CSS class mapping for frontend
STATUS_KELAS: dict[HETStatus, str] = {
    HETStatus.AMAN: "ok",
    HETStatus.WASPADA: "warn",
    HETStatus.KRITIS: "danger",
    HETStatus.MELAMPAUI: "danger",
    HETStatus.TIDAK_TERSEDIA: "muted",
}


def _determine_status(pct_of_het: float) -> HETStatus:
    """Determine HET status from percentage of HET price.

    Args:
        pct_of_het: Current price as percentage of HET (e.g., 95.0 = 95%)

    Returns:
        HETStatus enum value.
    """
    if pct_of_het > HET_MELAMPAUI_PCT * 100:
        return HETStatus.MELAMPAUI
    elif pct_of_het >= HET_KRITIS_PCT * 100:
        return HETStatus.KRITIS
    elif pct_of_het >= HET_WASPADA_PCT * 100:
        return HETStatus.WASPADA
    else:
        return HETStatus.AMAN


def _status_description(status: HETStatus, pct: float, selisih: int) -> str:
    """Generate human-readable description for a status."""
    descriptions = {
        HETStatus.AMAN: (
            f"Harga masih {100 - pct:.0f}% di bawah HET — "
            f"selisih Rp {abs(selisih):,}"
        ),
        HETStatus.WASPADA: (
            f"Harga sudah mencapai {pct:.0f}% dari HET — "
            f"sisa Rp {abs(selisih):,} sebelum mencapai batas"
        ),
        HETStatus.KRITIS: (
            f"Harga sudah mencapai batas HET ({pct:.0f}%) — "
            f"perlu pemantauan intensif"
        ),
        HETStatus.MELAMPAUI: (
            f"Harga melampaui HET sebesar {pct - 100:.0f}% "
            f"(+Rp {selisih:,}) — perlu intervensi segera"
        ),
    }
    return descriptions.get(status, "")


def check_het_status(
    comcat_id: str,
    current_price: int,
    komoditas_nama: str = "",
) -> HETResult:
    """
    Compare current price against HET reference for one komoditas.

    Args:
        comcat_id: Commodity category ID (e.g., "com_11")
        current_price: Current average price in Rp
        komoditas_nama: Display name (optional)

    Returns:
        HETResult with status, percentage, and description.
    """
    het_price = HET_REFERENCE.get(comcat_id)

    if het_price is None or het_price <= 0:
        return HETResult(
            comcat_id=comcat_id,
            komoditas_nama=komoditas_nama,
            status=HETStatus.TIDAK_TERSEDIA,
            harga_aktual=current_price,
            keterangan="Data HET tidak tersedia untuk komoditas ini",
        )

    if current_price <= 0:
        return HETResult(
            comcat_id=comcat_id,
            komoditas_nama=komoditas_nama,
            status=HETStatus.TIDAK_TERSEDIA,
            harga_aktual=current_price,
            het_harga=het_price,
            keterangan="Harga aktual tidak valid",
        )

    pct_of_het = (current_price / het_price) * 100
    selisih = current_price - het_price
    status = _determine_status(pct_of_het)

    return HETResult(
        comcat_id=comcat_id,
        komoditas_nama=komoditas_nama,
        status=status,
        harga_aktual=current_price,
        het_harga=het_price,
        pct_of_het=round(pct_of_het, 1),
        selisih=selisih,
        keterangan=_status_description(status, pct_of_het, selisih),
    )


def check_het_all(
    commodity_prices: dict[str, tuple[int, str]],
) -> list[HETResult]:
    """
    Check HET status for multiple komoditas at once.

    Args:
        commodity_prices: Dict of comcat_id → (current_price, komoditas_nama)

    Returns:
        List of HETResult sorted by severity (melampaui first).
    """
    results = []
    for comcat_id, (price, nama) in commodity_prices.items():
        result = check_het_status(comcat_id, price, nama)
        results.append(result)

    # Sort by severity: melampaui > kritis > waspada > aman > tidak_tersedia
    severity_order = {
        HETStatus.MELAMPAUI: 0,
        HETStatus.KRITIS: 1,
        HETStatus.WASPADA: 2,
        HETStatus.AMAN: 3,
        HETStatus.TIDAK_TERSEDIA: 4,
    }
    results.sort(key=lambda r: severity_order.get(r.status, 99))
    return results


def get_het_summary(results: list[HETResult]) -> dict:
    """
    Generate summary counts from HET results.

    Returns:
        Dict with count per status + total.
    """
    summary = {status.value: 0 for status in HETStatus}
    for r in results:
        summary[r.status.value] += 1

    return {
        "total": len(results),
        "per_status": summary,
        "ada_melampaui": summary.get("melampaui", 0) > 0,
        "ada_kritis": summary.get("kritis", 0) > 0,
    }

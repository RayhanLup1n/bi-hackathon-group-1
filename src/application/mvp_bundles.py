"""
Review Bundle Engine — group recommendations into coordinated review packages.

Three strategies:
  1. risk_cluster — group by high/critical risk level
  2. commodity_family — group related commodities (cabai family, bawang family)
  3. confidence_gap — highlight recommendations with low data confidence

Pure domain logic — no DB, no I/O. Takes a list of recommendation dicts
(from mvp_orchestrator), returns a list of Bundle dicts.
"""
from __future__ import annotations

from typing import Any

# ── Commodity families ──────────────────────────────────────────────────────
# Maps family name to commodity name substrings for matching.
# ponytail: if new commodities are added, extend these tuples.

COMMODITY_FAMILIES: dict[str, tuple[str, ...]] = {
    "Cabai": (
        "Cabai Merah Besar", "Cabai Merah Keriting",
        "Cabai Rawit Hijau", "Cabai Rawit Merah",
    ),
    "Bawang": ("Bawang Merah", "Bawang Putih"),
}

# ── Risk ordering for severity comparison ───────────────────────────────────

_RISK_ORDER: dict[str, int] = {"rendah": 0, "sedang": 1, "tinggi": 2, "kritis": 3}


def _max_risk(a: str, b: str) -> str:
    """Return the higher severity risk level."""
    return a if _RISK_ORDER.get(a, 0) >= _RISK_ORDER.get(b, 0) else b


def _highest_risk(commodities: list[dict]) -> str:
    """Find the highest risk level among a list of commodity dicts."""
    top = "rendah"
    for c in commodities:
        rl = c.get("risk_level", "rendah")
        if _RISK_ORDER.get(rl, 0) > _RISK_ORDER.get(top, 0):
            top = rl
    return top


def _dedupe_missing(items: list[str]) -> list[str]:
    """Deduplicate missing_information preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _to_bundle_commodity(rec: dict) -> dict:
    """Extract BundleCommodity fields from a recommendation dict."""
    return {
        "recommendation_id": str(rec.get("recommendation_id", "")),
        "name": str(rec.get("commodity", "")),
        "risk_level": str(rec.get("risk_level", "rendah")),
        "display_priority_score": float(rec.get("display_priority_score", 0.0)),
    }


def _avg_priority_score(recs: list[dict]) -> float:
    """Average display_priority_score across a group."""
    if not recs:
        return 0.0
    return round(
        sum(r.get("display_priority_score", 0.0) for r in recs) / len(recs),
        2,
    )


# ── Strategy functions ──────────────────────────────────────────────────────

def _build_risk_clusters(recommendations: list[dict]) -> list[dict]:
    """Group by kritis and tinggi risk levels. Each group with >=2 members."""
    bundles: list[dict] = []

    for risk_level, label in [("kritis", "Kritis"), ("tinggi", "Tinggi")]:
        group = [r for r in recommendations if r.get("risk_level") == risk_level]
        if len(group) < 2:
            continue

        commodities = [_to_bundle_commodity(r) for r in group]
        missing_all: list[str] = []
        for r in group:
            for m in r.get("missing_information", []):
                missing_all.append(str(m))

        bundles.append({
            "bundle_id": f"bundle_risk_{risk_level}",
            "name": f"Paket Tinjauan Risiko {label}",
            "reason": (
                f"{len(group)} komoditas menunjukkan risiko {risk_level} "
                f"dalam horizon 7 hari"
            ),
            "bundle_type": "risk_cluster",
            "commodities": commodities,
            "missing_information": _dedupe_missing(missing_all),
            "priority_score": _avg_priority_score(group),
        })

    return bundles


def _build_commodity_families(recommendations: list[dict]) -> list[dict]:
    """Group related commodities. Only includes commodities with risk >= sedang."""
    bundles: list[dict] = []

    for family, names in COMMODITY_FAMILIES.items():
        group = [
            r for r in recommendations
            if r.get("commodity", "") in names
            and _RISK_ORDER.get(r.get("risk_level", "rendah"), 0) >= _RISK_ORDER["sedang"]
        ]
        if len(group) < 2:
            continue

        commodities = [_to_bundle_commodity(r) for r in group]
        missing_all: list[str] = []
        for r in group:
            for m in r.get("missing_information", []):
                missing_all.append(str(m))

        highest = _highest_risk(group)
        total_eligible = len([
            r for r in recommendations
            if r.get("commodity", "") in names
        ])

        bundles.append({
            "bundle_id": f"bundle_family_{family.lower()}",
            "name": f"Paket Tinjauan Komoditas {family}",
            "reason": (
                f"{len(group)}/{total_eligible} komoditas {family.lower()} "
                f"menunjukkan risiko {highest}"
            ),
            "bundle_type": "commodity_family",
            "commodities": commodities,
            "missing_information": _dedupe_missing(missing_all),
            "priority_score": _avg_priority_score(group),
        })

    return bundles


def _build_confidence_gaps(recommendations: list[dict]) -> list[dict]:
    """Highlight recommendations with low confidence. Min 1 member (single is valid)."""
    group = [
        r for r in recommendations
        if r.get("confidence_level") == "low"
    ]
    if len(group) < 1:
        return []

    commodities = [_to_bundle_commodity(r) for r in group]
    missing_all: list[str] = []
    for r in group:
        for m in r.get("missing_information", []):
            missing_all.append(str(m))

    return [{
        "bundle_id": "bundle_confidence_gap",
        "name": "Paket Verifikasi Data",
        "reason": (
            f"{len(group)} rekomendasi memerlukan verifikasi data "
            f"tambahan karena confidence rendah"
        ),
        "bundle_type": "confidence_gap",
        "commodities": commodities,
        "missing_information": _dedupe_missing(missing_all),
        "priority_score": _avg_priority_score(group),
    }]


# ── Public API ──────────────────────────────────────────────────────────────

def generate_bundles(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate review bundles from a list of recommendation dicts.

    Applies all three strategies:
      1. risk_cluster — kritis + tinggi groups (>=2 members each)
      2. commodity_family — cabai + bawang families (>=2 members with risk >= sedang)
      3. confidence_gap — low-confidence recs (>=1 member)

    Returns bundles sorted by priority_score descending (highest risk first).
    """
    bundles: list[dict] = []
    bundles.extend(_build_risk_clusters(recommendations))
    bundles.extend(_build_commodity_families(recommendations))
    bundles.extend(_build_confidence_gaps(recommendations))

    # Sort by priority_score descending
    bundles.sort(key=lambda b: b["priority_score"], reverse=True)

    return bundles

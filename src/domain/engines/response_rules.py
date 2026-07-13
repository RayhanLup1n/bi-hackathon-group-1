"""
Response option rule engine — deterministic mapping from risk + confidence to
allowed response options.

Rules follow PRD Section 13 P0-08:
  - Rendah  → Monitor only
  - Sedang  → Verifikasi, Monitoring intensif
  - Tinggi  → Verifikasi, Koordinasikan, optional Koordinasi distribusi
  - Kritis  → Eskalasi human review, Pertimbangkan Intervensi

Confidence gate: when confidence is "low", response options are capped at
"Verifikasi" regardless of risk level. This implements the PRD rule:
"Ketika confidence rendah, sistem tidak boleh memberikan response option
yang lebih spesifik daripada Verifikasi."

No external dependencies — pure deterministic mapping.
"""
from __future__ import annotations

from src.domain.schemas.decision import ConfidenceLevel, ResponseOption, ResponseType


# ── Response option definitions ─────────────────────────────────────────────

_OPTIONS: dict[ResponseType, dict[str, str]] = {
    ResponseType.MONITOR: {
        "label": "Pantau harga harian",
        "description": "Lanjutkan pemantauan rutin. Tidak ada tindakan khusus yang diperlukan.",
    },
    ResponseType.VERIFIKASI: {
        "label": "Verifikasi harga dan data",
        "description": (
            "Periksa harga pada sumber alternatif (PIHPS, pasar terdekat). "
            "Konfirmasi apakah kenaikan bersifat sementara atau persisten."
        ),
    },
    ResponseType.KOORDINASIKAN: {
        "label": "Koordinasikan tinjauan",
        "description": (
            "Jadwalkan pembahasan dengan dinas terkait. "
            "Siapkan data pendukung untuk rapat koordinasi."
        ),
    },
    ResponseType.PERTIMBANGKAN_INTERVENSI: {
        "label": "Pertimbangkan evaluasi intervensi",
        "description": (
            "Eskalasi ke pengambil keputusan TPID. "
            "Kumpulkan data stok, logistik, dan opsi operasi pasar. "
            "Keputusan intervensi tetap berada pada otoritas resmi."
        ),
    },
}

# ── Risk-level to allowed response types ────────────────────────────────────

_RISK_RESPONSE_MAP: dict[str, list[ResponseType]] = {
    "rendah": [ResponseType.MONITOR],
    "sedang": [ResponseType.VERIFIKASI, ResponseType.MONITOR],
    "tinggi": [
        ResponseType.VERIFIKASI,
        ResponseType.KOORDINASIKAN,
        ResponseType.MONITOR,
    ],
    "kritis": [
        ResponseType.VERIFIKASI,
        ResponseType.KOORDINASIKAN,
        ResponseType.PERTIMBANGKAN_INTERVENSI,
        ResponseType.MONITOR,
    ],
}

# ── Confidence cap: low confidence restricts to VERIFIKASI max ──────────────

_CONFIDENCE_CAP: dict[ConfidenceLevel, ResponseType] = {
    "high": ResponseType.PERTIMBANGKAN_INTERVENSI,
    "medium": ResponseType.KOORDINASIKAN,
    "low": ResponseType.VERIFIKASI,
}


def _response_type_rank(response_type: ResponseType) -> int:
    """Order for capping: Monitor=0, Verifikasi=1, Koordinasikan=2, Intervensi=3."""
    _order = {
        ResponseType.MONITOR: 0,
        ResponseType.VERIFIKASI: 1,
        ResponseType.KOORDINASIKAN: 2,
        ResponseType.PERTIMBANGKAN_INTERVENSI: 3,
    }
    return _order[response_type]


def get_response_options(
    risk_level: str,
    confidence_level: ConfidenceLevel,
) -> list[ResponseOption]:
    """Return allowed response options for a given risk and confidence.

    Args:
        risk_level: One of "rendah", "sedang", "tinggi", "kritis".
        confidence_level: "high", "medium", or "low".

    Returns:
        List of ResponseOption, ordered from least to most assertive.
    """
    risk_key = risk_level.lower().strip()
    allowed_types = _RISK_RESPONSE_MAP.get(risk_key, [ResponseType.MONITOR])

    # Apply confidence cap — remove options above the cap
    cap = _CONFIDENCE_CAP.get(confidence_level, ResponseType.VERIFIKASI)
    cap_rank = _response_type_rank(cap)
    allowed_types = [
        t for t in allowed_types if _response_type_rank(t) <= cap_rank
    ]

    # Build ResponseOption objects, sorted least-assertive first
    options = [
        ResponseOption(
            type=t,
            label=_OPTIONS[t]["label"],
            description=_OPTIONS[t]["description"],
        )
        for t in sorted(allowed_types, key=_response_type_rank)
    ]

    return options


def get_next_step(risk_level: str, confidence_level: ConfidenceLevel) -> str:
    """Return the recommended next step text based on risk and confidence.

    This is the human-readable version of the top response option.
    """
    options = get_response_options(risk_level, confidence_level)
    if not options:
        return "Monitor"

    # The most assertive option dictates the next step
    top = max(options, key=lambda o: _response_type_rank(o.type))

    next_steps = {
        ResponseType.MONITOR: "Monitor harga harian",
        ResponseType.VERIFIKASI: "Verifikasi harga dan data",
        ResponseType.KOORDINASIKAN: "Koordinasikan tinjauan dengan dinas terkait",
        ResponseType.PERTIMBANGKAN_INTERVENSI: (
            "Eskalasi untuk evaluasi intervensi oleh pengambil keputusan TPID"
        ),
    }
    return next_steps.get(top.type, "Monitor")

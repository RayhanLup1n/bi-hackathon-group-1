"""
Bowtie Analysis Engine — maps FTA threats to prevention & mitigation barriers.

Bowtie model:
    PREVENTION BARRIERS → HAZARD EVENT → MITIGATION BARRIERS

Each FTA threat has associated prevention barriers (left side)
and mitigation barriers (right side). Active threats activate
their corresponding barriers as "relevant".

Integration:
    1. Run FTA/RCA engine to get active threats
    2. Pass RCAResult to run_bowtie() to generate barrier analysis
    3. Return BowtieResult with activated prevention + mitigation
"""
from __future__ import annotations

from pydantic import BaseModel

from src.domain.schemas.models import RCAResult


# ──────────────────────────────────────────────
# RESPONSE SCHEMAS
# ──────────────────────────────────────────────

class Barrier(BaseModel):
    id: str
    name: str
    description: str
    threat_ids: list[str]  # which threats this barrier addresses
    active: bool = False   # True if related threat is active


class BowtieResult(BaseModel):
    commodity_key: str
    commodity_name: str
    hazard_event: str
    severity_level: str
    active_threats: list[dict]
    prevention: list[Barrier]
    mitigation: list[Barrier]
    summary: str


# ──────────────────────────────────────────────
# FTA THREAT DEFINITIONS
# ──────────────────────────────────────────────

FTA_THREATS: list[dict] = [
    {
        "id": "D1",
        "name": "Hari Raya / Musim Perayaan",
        "type": "demand",
        "desc": "Lonjakan permintaan menjelang hari raya besar",
    },
    {
        "id": "D2",
        "name": "Tekanan Ekonomi",
        "type": "demand",
        "desc": "Inflasi pangan berkelanjutan, daya beli melemah",
    },
    {
        "id": "S1",
        "name": "Cuaca Ekstrem",
        "type": "supply",
        "desc": "Gangguan cuaca di daerah produksi utama",
    },
    {
        "id": "S2",
        "name": "Defisit Stok Nasional",
        "type": "supply",
        "desc": "Stok nasional di bawah kebutuhan bulanan",
    },
    {
        "id": "S3",
        "name": "Ketimpangan Distribusi",
        "type": "supply",
        "desc": "Kenaikan harga tidak merata antar wilayah",
    },
    {
        "id": "S4",
        "name": "Musim Off-Season",
        "type": "supply",
        "desc": "Periode off-season komoditas, pasokan berkurang",
    },
]


# ──────────────────────────────────────────────
# BARRIER DEFINITIONS
# Each barrier is linked to one or more threat IDs
# ──────────────────────────────────────────────

PREVENTION_BARRIERS: list[dict] = [
    {
        "id": "P1",
        "name": "Early Warning H-14 Hari Raya",
        "description": "Notifikasi otomatis 14 hari sebelum hari raya untuk antisipasi lonjakan permintaan",
        "threat_ids": ["D1"],
    },
    {
        "id": "P2",
        "name": "Monitor Indeks Harga Konsumen",
        "description": "Pantau tren IHK bulanan untuk deteksi dini tekanan inflasi pangan",
        "threat_ids": ["D2"],
    },
    {
        "id": "P3",
        "name": "Monitor Cuaca Open-Meteo",
        "description": "Pemantauan cuaca harian di daerah produksi utama (hujan, suhu, angin, kekeringan)",
        "threat_ids": ["S1"],
    },
    {
        "id": "P4",
        "name": "Monitor Stok Mingguan",
        "description": "Pelaporan stok pedagang besar dan Bulog secara mingguan",
        "threat_ids": ["S2"],
    },
    {
        "id": "P5",
        "name": "Monitor Harga Antar Kota",
        "description": "Deteksi disparitas harga antar kota >20% sebagai sinyal gangguan distribusi",
        "threat_ids": ["S3"],
    },
    {
        "id": "P6",
        "name": "Kalender Panen Terpadu",
        "description": "Pemetaan jadwal panen per wilayah untuk antisipasi periode off-season",
        "threat_ids": ["S4"],
    },
]

MITIGATION_BARRIERS: list[dict] = [
    {
        "id": "M1",
        "name": "Operasi Pasar Darurat",
        "description": "Penjualan langsung di titik keramaian dengan harga subsidi untuk meredam demand spike",
        "threat_ids": ["D1", "D2"],
    },
    {
        "id": "M2",
        "name": "Importasi Darurat Fast-Track",
        "description": "Percepatan izin impor komoditas kritis saat supply domestik terganggu",
        "threat_ids": ["S1", "S2"],
    },
    {
        "id": "M3",
        "name": "Release Cadangan Bulog",
        "description": "Lepas cadangan pangan nasional ke pasar untuk stabilisasi harga",
        "threat_ids": ["S2", "S4"],
    },
    {
        "id": "M4",
        "name": "Koordinasi Transportasi Lintas Daerah",
        "description": "Fasilitasi logistik dari daerah surplus ke daerah defisit",
        "threat_ids": ["S3"],
    },
    {
        "id": "M5",
        "name": "Komunikasi Publik & Transparansi Harga",
        "description": "Publikasi data harga real-time untuk meredam ekspektasi inflasi spekulatif",
        "threat_ids": ["D2"],
    },
    {
        "id": "M6",
        "name": "Diversifikasi Sumber Pasokan",
        "description": "Alihkan sourcing ke wilayah yang sedang panen untuk tutupi defisit off-season",
        "threat_ids": ["S1", "S4"],
    },
]


# ──────────────────────────────────────────────
# ENGINE
# ──────────────────────────────────────────────

def _map_rca_to_threats(rca: RCAResult) -> list[str]:
    """Map RCA engine results to active FTA threat IDs.

    Mapping from RCA checks/indicators to FTA threats:
        Check 1 (Hari Raya) triggered    → D1
        Check 2 (Cuaca) triggered        → S1
        Check 3 (Persebaran Kota) triggered → S3
        Check 4 (Stok) triggered         → S2
        Indicator "D1: Window Hari Raya"  → D1
        Indicator "S1: Cuaca Ekstrem"     → S1
        Indicator "S3: Stok Menipis"      → S2  (severity indicator S3 maps to threat S2)
        Indicator "T2: Kenaikan Serempak" → S3
        is_anomaly + no specific trigger  → D2 (ekspektatif)

    Note: S4 (Off-Season) has no RCA mapping yet — barrier P6/M3/M6 won't activate.
    """
    active: set[str] = set()

    # From sequential checks
    for check in rca.checks:
        if check.status != "triggered":
            continue
        if check.step == 1:
            active.add("D1")
        elif check.step == 2:
            active.add("S1")
        elif check.step == 3:
            active.add("S3")
        elif check.step == 4:
            active.add("S2")

    # From severity indicators (may add extras not caught by early-exit)
    for ind in rca.yes_indicators:
        if ind.startswith("D1"):
            active.add("D1")
        elif ind.startswith("S1"):
            active.add("S1")
        elif ind.startswith("S3"):
            active.add("S2")
        elif ind.startswith("T2"):
            active.add("S3")

    # If anomaly detected but no specific trigger → ekspektatif pressure (D2)
    if rca.is_anomaly and not active:
        active.add("D2")

    return sorted(active)


def run_bowtie(rca: RCAResult) -> BowtieResult:
    """Generate Bowtie analysis from FTA/RCA result.

    Args:
        rca: Result from rca_engine.run_rca()

    Returns:
        BowtieResult with active threats and activated barriers.
    """
    active_threat_ids = _map_rca_to_threats(rca)

    # Build active threats info
    active_threats = []
    for threat in FTA_THREATS:
        is_active = threat["id"] in active_threat_ids
        active_threats.append({
            "id": threat["id"],
            "name": threat["name"],
            "type": threat["type"],
            "desc": threat["desc"],
            "active": is_active,
        })

    # Build prevention barriers with activation status
    prevention = []
    for b in PREVENTION_BARRIERS:
        is_active = any(tid in active_threat_ids for tid in b["threat_ids"])
        prevention.append(Barrier(
            id=b["id"],
            name=b["name"],
            description=b["description"],
            threat_ids=b["threat_ids"],
            active=is_active,
        ))

    # Build mitigation barriers with activation status
    mitigation = []
    for b in MITIGATION_BARRIERS:
        is_active = any(tid in active_threat_ids for tid in b["threat_ids"])
        mitigation.append(Barrier(
            id=b["id"],
            name=b["name"],
            description=b["description"],
            threat_ids=b["threat_ids"],
            active=is_active,
        ))

    # Generate summary
    n_active = len(active_threat_ids)
    n_prevention = sum(1 for b in prevention if b.active)
    n_mitigation = sum(1 for b in mitigation if b.active)

    if n_active == 0:
        summary = "Tidak ada ancaman aktif terdeteksi. Semua barrier dalam status standby."
    else:
        threat_names = [
            t["name"] for t in FTA_THREATS if t["id"] in active_threat_ids
        ]
        summary = (
            f"{n_active} ancaman aktif: {', '.join(threat_names)}. "
            f"{n_prevention} barrier pencegahan dan {n_mitigation} barrier mitigasi diaktifkan."
        )

    return BowtieResult(
        commodity_key=rca.commodity_key,
        commodity_name=rca.commodity_name,
        hazard_event="Anomali Harga Naik Signifikan",
        severity_level=rca.severity_level,
        active_threats=active_threats,
        prevention=prevention,
        mitigation=mitigation,
        summary=summary,
    )

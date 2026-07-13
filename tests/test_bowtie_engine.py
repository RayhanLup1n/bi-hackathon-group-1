"""
Tests for Bowtie Analysis Engine (src/engine/bowtie_engine.py).

Tests:
  - Threat mapping from RCA checks and indicators
  - Prevention barrier activation
  - Mitigation barrier activation
  - Summary text generation
  - Edge cases: no threats, all threats, single threat
"""
import pytest
from datetime import date
from unittest.mock import patch

from src.domain.schemas.models import (
    CommodityData, CuacaInfo, KotaInfo, StokInfo,
    CheckResult, RCAResult, DiagnosisType,
)
from src.domain.engines.bowtie_engine import (
    run_bowtie, _map_rca_to_threats,
    FTA_THREATS, PREVENTION_BARRIERS, MITIGATION_BARRIERS,
    Barrier, BowtieResult,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def make_rca_result(
    checks: list[dict] | None = None,
    yes_indicators: list[str] | None = None,
    is_anomaly: bool = True,
    severity_level: str = "L1",
    diagnosis: str = "demand",
) -> RCAResult:
    """Factory for RCAResult with sane defaults."""
    default_checks = [
        {"step": 1, "nama": "Cek Hari Raya", "status": "clear", "detail": "—"},
        {"step": 2, "nama": "Cek Cuaca", "status": "skip", "detail": "—"},
        {"step": 3, "nama": "Cek Persebaran", "status": "skip", "detail": "—"},
        {"step": 4, "nama": "Cek Stok", "status": "skip", "detail": "—"},
    ]
    if checks:
        for override in checks:
            idx = override["step"] - 1
            default_checks[idx].update(override)

    return RCAResult(
        commodity_key="test",
        commodity_name="Test Komoditas",
        diagnosis=DiagnosisType(diagnosis),
        title="Test",
        description="Test",
        action="Test",
        checks=[CheckResult(**c) for c in default_checks],
        price_delta_pct=12.0,
        is_anomaly=is_anomaly,
        severity_level=severity_level,
        yes_indicators=yes_indicators or [],
    )


# ── FTA THREAT DEFINITIONS ──────────────────────────────────────────────────


class TestFTADefinitions:
    """Verify threat and barrier definitions are complete and consistent."""

    def test_fta_has_6_threats(self):
        assert len(FTA_THREATS) == 6

    def test_threat_ids_unique(self):
        ids = [t["id"] for t in FTA_THREATS]
        assert len(ids) == len(set(ids))

    def test_threat_types_valid(self):
        for t in FTA_THREATS:
            assert t["type"] in ("demand", "supply"), f"Invalid type for {t['id']}"

    def test_prevention_has_6_barriers(self):
        assert len(PREVENTION_BARRIERS) == 6

    def test_mitigation_has_6_barriers(self):
        assert len(MITIGATION_BARRIERS) == 6

    def test_barrier_ids_unique(self):
        all_ids = [b["id"] for b in PREVENTION_BARRIERS + MITIGATION_BARRIERS]
        assert len(all_ids) == len(set(all_ids))

    def test_barrier_threat_ids_are_valid(self):
        """All threat_ids referenced in barriers must exist in FTA_THREATS."""
        valid_ids = {t["id"] for t in FTA_THREATS}
        for b in PREVENTION_BARRIERS + MITIGATION_BARRIERS:
            for tid in b["threat_ids"]:
                assert tid in valid_ids, (
                    f"Barrier {b['id']} references unknown threat {tid}"
                )


# ── THREAT MAPPING ──────────────────────────────────────────────────────────


class TestMapRcaToThreats:
    """Tests for _map_rca_to_threats() — maps RCA output to FTA threat IDs."""

    def test_hari_raya_triggered_maps_to_D1(self):
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        threats = _map_rca_to_threats(rca)
        assert "D1" in threats

    def test_cuaca_triggered_maps_to_S1(self):
        rca = make_rca_result(checks=[{"step": 2, "status": "triggered"}])
        threats = _map_rca_to_threats(rca)
        assert "S1" in threats

    def test_persebaran_triggered_maps_to_S3(self):
        rca = make_rca_result(checks=[{"step": 3, "status": "triggered"}])
        threats = _map_rca_to_threats(rca)
        assert "S3" in threats

    def test_stok_triggered_maps_to_S2(self):
        rca = make_rca_result(checks=[{"step": 4, "status": "triggered"}])
        threats = _map_rca_to_threats(rca)
        assert "S2" in threats

    def test_indicator_D1_maps_to_D1(self):
        rca = make_rca_result(yes_indicators=["D1: Window Hari Raya"])
        threats = _map_rca_to_threats(rca)
        assert "D1" in threats

    def test_indicator_S1_maps_to_S1(self):
        rca = make_rca_result(yes_indicators=["S1: Cuaca Ekstrem"])
        threats = _map_rca_to_threats(rca)
        assert "S1" in threats

    def test_indicator_S3_maps_to_S2(self):
        """Severity indicator S3 (Stok Menipis) maps to threat S2 (Defisit Stok)."""
        rca = make_rca_result(yes_indicators=["S3: Stok Menipis"])
        threats = _map_rca_to_threats(rca)
        assert "S2" in threats

    def test_indicator_T2_maps_to_S3(self):
        """Severity indicator T2 (Kenaikan Serempak) maps to threat S3 (Distribusi)."""
        rca = make_rca_result(yes_indicators=["T2: Kenaikan Serempak"])
        threats = _map_rca_to_threats(rca)
        assert "S3" in threats

    def test_anomaly_no_trigger_maps_to_D2(self):
        """If anomaly detected but no specific trigger → D2 (Tekanan Ekonomi)."""
        rca = make_rca_result(is_anomaly=True, checks=None, yes_indicators=[])
        threats = _map_rca_to_threats(rca)
        assert "D2" in threats

    def test_no_anomaly_no_trigger_returns_empty(self):
        """No anomaly, no triggers → no active threats."""
        rca = make_rca_result(is_anomaly=False, checks=None, yes_indicators=[])
        threats = _map_rca_to_threats(rca)
        assert threats == []

    def test_multiple_triggers_combine(self):
        """Multiple triggers should all be present."""
        rca = make_rca_result(
            checks=[
                {"step": 1, "status": "triggered"},
                {"step": 2, "status": "triggered"},
            ],
            yes_indicators=["S3: Stok Menipis"],
        )
        threats = _map_rca_to_threats(rca)
        assert "D1" in threats
        assert "S1" in threats
        assert "S2" in threats

    def test_output_is_sorted(self):
        """Threat IDs should be returned sorted."""
        rca = make_rca_result(
            checks=[
                {"step": 3, "status": "triggered"},
                {"step": 1, "status": "triggered"},
            ],
        )
        threats = _map_rca_to_threats(rca)
        assert threats == sorted(threats)

    def test_clear_checks_not_mapped(self):
        """Clear status checks should NOT map to threats."""
        rca = make_rca_result(checks=[{"step": 1, "status": "clear"}])
        threats = _map_rca_to_threats(rca)
        assert "D1" not in threats


# ── BARRIER ACTIVATION ──────────────────────────────────────────────────────


class TestBarrierActivation:
    """Tests for barrier activation logic in run_bowtie()."""

    def test_d1_activates_P1_and_M1(self):
        """D1 threat activates P1 (prevention) and M1 (mitigation)."""
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        result = run_bowtie(rca)

        p1 = next(b for b in result.prevention if b.id == "P1")
        m1 = next(b for b in result.mitigation if b.id == "M1")
        assert p1.active is True
        assert m1.active is True

    def test_s1_activates_P3_M2_M6(self):
        """S1 threat activates P3, M2, M6."""
        rca = make_rca_result(checks=[{"step": 2, "status": "triggered"}])
        result = run_bowtie(rca)

        active_ids = [b.id for b in result.prevention + result.mitigation if b.active]
        assert "P3" in active_ids
        assert "M2" in active_ids
        assert "M6" in active_ids

    def test_s2_activates_P4_M2_M3(self):
        """S2 threat activates P4, M2, M3."""
        rca = make_rca_result(checks=[{"step": 4, "status": "triggered"}])
        result = run_bowtie(rca)

        active_ids = [b.id for b in result.prevention + result.mitigation if b.active]
        assert "P4" in active_ids
        assert "M2" in active_ids
        assert "M3" in active_ids

    def test_no_threats_all_barriers_inactive(self):
        """No active threats → all barriers should be inactive."""
        rca = make_rca_result(is_anomaly=False)
        result = run_bowtie(rca)

        assert all(b.active is False for b in result.prevention)
        assert all(b.active is False for b in result.mitigation)

    def test_barrier_always_has_12_items(self):
        """Should always return 6 prevention + 6 mitigation barriers."""
        rca = make_rca_result()
        result = run_bowtie(rca)

        assert len(result.prevention) == 6
        assert len(result.mitigation) == 6

    def test_shared_barrier_activates_from_either_threat(self):
        """M2 is linked to S1 and S2 — either alone should activate it."""
        # S1 only
        rca_s1 = make_rca_result(checks=[{"step": 2, "status": "triggered"}])
        result_s1 = run_bowtie(rca_s1)
        m2_s1 = next(b for b in result_s1.mitigation if b.id == "M2")
        assert m2_s1.active is True

        # S2 only
        rca_s2 = make_rca_result(checks=[{"step": 4, "status": "triggered"}])
        result_s2 = run_bowtie(rca_s2)
        m2_s2 = next(b for b in result_s2.mitigation if b.id == "M2")
        assert m2_s2.active is True


# ── RUN BOWTIE FULL RESULT ──────────────────────────────────────────────────


class TestRunBowtie:
    """Tests for the full run_bowtie() function."""

    def test_result_fields_populated(self):
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        result = run_bowtie(rca)

        assert result.commodity_key == "test"
        assert result.commodity_name == "Test Komoditas"
        assert result.hazard_event == "Anomali Harga Naik Signifikan"
        assert len(result.active_threats) == 6  # always 6, with active flags
        assert len(result.prevention) == 6
        assert len(result.mitigation) == 6
        assert len(result.summary) > 0

    def test_active_threats_have_correct_flags(self):
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        result = run_bowtie(rca)

        d1 = next(t for t in result.active_threats if t["id"] == "D1")
        d2 = next(t for t in result.active_threats if t["id"] == "D2")
        assert d1["active"] is True
        assert d2["active"] is False

    def test_summary_no_threats(self):
        rca = make_rca_result(is_anomaly=False)
        result = run_bowtie(rca)

        assert "Tidak ada ancaman aktif" in result.summary
        assert "standby" in result.summary

    def test_summary_with_threats(self):
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        result = run_bowtie(rca)

        assert "1 ancaman aktif" in result.summary
        assert "Hari Raya" in result.summary
        assert "barrier" in result.summary.lower() or "diaktifkan" in result.summary

    def test_severity_level_passthrough(self):
        """Severity level from RCA should pass through to BowtieResult."""
        rca = make_rca_result(severity_level="L3")
        result = run_bowtie(rca)
        assert result.severity_level == "L3"

    def test_result_is_serializable(self):
        """BowtieResult should be JSON-serializable via Pydantic."""
        rca = make_rca_result(checks=[{"step": 1, "status": "triggered"}])
        result = run_bowtie(rca)

        data = result.model_dump()
        assert isinstance(data, dict)
        assert "prevention" in data
        assert "mitigation" in data
        assert "active_threats" in data

    def test_s4_not_activated_by_rca(self):
        """S4 (Off-Season) has no RCA mapping — should never activate."""
        # Trigger all possible checks
        rca = make_rca_result(
            checks=[
                {"step": 1, "status": "triggered"},
                {"step": 2, "status": "triggered"},
                {"step": 3, "status": "triggered"},
                {"step": 4, "status": "triggered"},
            ],
            yes_indicators=["G1: Anomali Harga", "D1: Window Hari Raya",
                          "S1: Cuaca Ekstrem", "S3: Stok Menipis",
                          "T2: Kenaikan Serempak"],
        )
        threats = _map_rca_to_threats(rca)
        assert "S4" not in threats

    def test_d2_only_as_fallback(self):
        """D2 should only activate when anomaly + no specific triggers."""
        # With specific triggers: D2 should NOT appear
        rca_with_trigger = make_rca_result(
            is_anomaly=True,
            checks=[{"step": 1, "status": "triggered"}],
        )
        threats = _map_rca_to_threats(rca_with_trigger)
        assert "D2" not in threats

        # Without triggers: D2 SHOULD appear
        rca_fallback = make_rca_result(is_anomaly=True)
        threats_fallback = _map_rca_to_threats(rca_fallback)
        assert "D2" in threats_fallback

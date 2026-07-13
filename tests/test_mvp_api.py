"""
Integration tests for MVP decision workflow endpoints.

Tests cover:
  - Recommendation schema contract
  - Priority score and confidence factor calculations
  - Response option rules (risk + confidence → allowed options)
  - Confidence gate (freshness, coverage, history, model performance)
  - Priority engine assembly
  - Graceful degradation patterns (missing signals)

These are unit/integration tests — no database or HTTP required.
"""
from __future__ import annotations

import pytest
from datetime import date

from src.domain.schemas.decision import (
    ConfidenceLevel,
    ConfidenceSignals,
    EvidenceItem,
    EvidenceKind,
    KnowledgeStatus,
    PrioritySignals,
    Recommendation,
    ResponseOption,
    ResponseType,
    SourceReference,
    calculate_confidence_factor,
    calculate_priority_score,
)
from src.domain.engines.response_rules import (
    get_next_step,
    get_response_options,
)
from src.domain.engines.confidence_gate import (
    build_confidence_signals,
    compute_coverage_signal,
    compute_freshness_signal,
    compute_history_signal,
    compute_model_performance_signal,
    is_confidence_too_low,
)
from src.domain.engines.priority_engine import (
    build_recommendation,
    _map_het_to_price_condition,
    _map_het_to_risk_level,
)


# ── Decision contract tests (from existing suite, verified) ─────────────────

class TestDecisionContract:
    """Verify the core decision schema and scoring functions."""

    def test_recommendation_always_requires_human_review(self):
        rec = Recommendation(
            recommendation_id="t1",
            commodity="Bawang Merah",
            region="Banten",
            price_condition="Normal",
            risk_level="rendah",
            time_horizon_days=7,
            priority_signals=PrioritySignals(),
            confidence_signals=ConfidenceSignals(),
            knowledge_status=KnowledgeStatus.FACT,
        )
        assert rec.requires_human_review is True

    def test_recommendation_rejects_empty_identity(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Recommendation(
                recommendation_id="",
                commodity="Bawang Merah",
                region="Banten",
                price_condition="Normal",
                risk_level="rendah",
                time_horizon_days=7,
                priority_signals=PrioritySignals(),
                confidence_signals=ConfidenceSignals(),
                knowledge_status=KnowledgeStatus.FACT,
            )

    def test_recommendation_rejects_negative_horizon(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Recommendation(
                recommendation_id="t2",
                commodity="Bawang Merah",
                region="Banten",
                price_condition="Normal",
                risk_level="rendah",
                time_horizon_days=0,
                priority_signals=PrioritySignals(),
                confidence_signals=ConfidenceSignals(),
                knowledge_status=KnowledgeStatus.FACT,
            )

    def test_full_score_high_confidence_recommendation(self):
        rec = Recommendation(
            recommendation_id="t3",
            commodity="Cabai Rawit Merah",
            region="Jawa Barat",
            price_condition="Melampaui Ambang",
            risk_level="kritis",
            time_horizon_days=7,
            priority_signals=PrioritySignals(
                price_position=1.0,
                forecast_p90_breach=1.0,
                momentum_anomaly=0.8,
                regional_spread=0.7,
                weather_calendar=0.5,
            ),
            confidence_signals=ConfidenceSignals(
                freshness=1.0,
                coverage=0.9,
                history=0.8,
                model_performance=0.7,
            ),
            observed_facts=[
                EvidenceItem(kind=EvidenceKind.FACT, label="HET", value="120%"),
            ],
            response_options=[
                ResponseOption(
                    type=ResponseType.VERIFIKASI,
                    label="Verifikasi harga pada sumber alternatif",
                ),
            ],
            sources=[SourceReference(name="PIHPS", cutoff="2026-07-13")],
            knowledge_status=KnowledgeStatus.MODEL_OUTPUT,
        )
        # Priority: 0.25+0.30+0.16+0.105+0.05 = 0.865 * 100 = 86.5
        assert rec.raw_priority_score == 86.5
        # Confidence: 0.30+0.225+0.16+0.175 = 0.86
        assert rec.confidence_factor == 0.86
        assert rec.confidence_level == "high"
        # Display: 86.5 * 0.86 = 74.39
        assert rec.display_priority_score == 74.39


# ── Response option rules tests ──────────────────────────────────────────────

class TestResponseRules:
    """Verify the deterministic response option mapping."""

    def test_rendah_returns_monitor_only(self):
        options = get_response_options("rendah", "high")
        assert len(options) == 1
        assert options[0].type == ResponseType.MONITOR

    def test_kritis_high_confidence_returns_intervention(self):
        options = get_response_options("kritis", "high")
        types = [o.type for o in options]
        assert ResponseType.PERTIMBANGKAN_INTERVENSI in types
        assert ResponseType.VERIFIKASI in types

    def test_confidence_low_caps_to_verifikasi(self):
        """Even kritis risk caps at Verifikasi when confidence is low."""
        options = get_response_options("kritis", "low")
        types = [o.type for o in options]
        assert ResponseType.PERTIMBANGKAN_INTERVENSI not in types
        assert ResponseType.KOORDINASIKAN not in types
        assert ResponseType.MONITOR in types

    def test_confidence_medium_caps_to_koordinasikan(self):
        options = get_response_options("kritis", "medium")
        types = [o.type for o in options]
        assert ResponseType.PERTIMBANGKAN_INTERVENSI not in types
        assert ResponseType.KOORDINASIKAN in types
        assert ResponseType.VERIFIKASI in types

    def test_next_step_matches_top_option(self):
        assert "Monitor" in get_next_step("rendah", "high")
        assert "Verifikasi" in get_next_step("sedang", "high")
        assert "Koordinasi" in get_next_step("tinggi", "high")
        assert "eskalasi" in get_next_step("kritis", "high").lower()

    def test_unknown_risk_level_defaults_to_monitor(self):
        options = get_response_options("nonexistent", "high")
        assert len(options) == 1
        assert options[0].type == ResponseType.MONITOR


# ── Confidence gate tests ────────────────────────────────────────────────────

class TestConfidenceGate:
    """Verify confidence signal computation."""

    def test_fresh_signal_max(self):
        assert compute_freshness_signal(0.0) == 1.0
        assert compute_freshness_signal(0.5) > 0.8

    def test_stale_signal_low(self):
        assert compute_freshness_signal(5.0) < 0.2
        assert compute_freshness_signal(10.0) < 0.1

    def test_coverage_signal_direct(self):
        assert compute_coverage_signal(1.0) == 1.0
        assert compute_coverage_signal(0.5) == 0.5
        assert compute_coverage_signal(1.5) == 1.0  # clamped
        assert compute_coverage_signal(-0.1) == 0.0  # clamped

    def test_history_signal(self):
        assert compute_history_signal(90, 90) == 1.0
        assert compute_history_signal(90, 45) == 0.5
        assert compute_history_signal(90, 180) == 1.0  # capped

    def test_model_performance_worse_than_baseline(self):
        assert compute_model_performance_signal(is_worse_than_baseline=True) == 0.2

    def test_model_performance_unknown(self):
        assert compute_model_performance_signal(wape=None) == 0.5

    def test_build_confidence_signals_integration(self):
        signals = build_confidence_signals(
            data_age_days=1.0,
            coverage_ratio=0.85,
            history_days=120,
            wape=4.5,
        )
        # freshness: exp(-0.4 * 1.0) ≈ 0.67
        assert 0.6 < signals.freshness <= 0.8
        assert signals.coverage == 0.85
        assert signals.history == 1.0  # 120 >= 90
        assert signals.model_performance == 0.85  # wape <= 5.0

    def test_is_confidence_too_low(self):
        assert is_confidence_too_low("low") is True
        assert is_confidence_too_low("medium") is False
        assert is_confidence_too_low("high") is False


# ── Priority engine tests ────────────────────────────────────────────────────

class TestPriorityEngine:
    """Verify the priority engine assembles recommendations correctly."""

    def test_build_minimal_recommendation(self):
        rec = build_recommendation(
            commodity_key="bawang_merah_test",
            commodity_name="Bawang Merah Test",
            province="Banten",
            province_id=11,
            price_now=45000,
            price_prev=42000,
        )
        assert rec.commodity == "Bawang Merah Test"
        assert rec.region == "Banten"
        assert rec.time_horizon_days == 7
        assert rec.requires_human_review is True
        assert rec.recommendation_id.startswith("rec_")
        assert len(rec.observed_facts) > 0
        assert len(rec.response_options) > 0
        assert len(rec.sources) > 0
        assert "Volume stok" in rec.missing_information

    def test_build_with_het_breach(self):
        rec = build_recommendation(
            commodity_key="cabai_merah_test",
            commodity_name="Cabai Merah Test",
            province="Jawa Barat",
            province_id=12,
            het_pct=110.0,
            het_status="melampaui",
            price_now=65000,
            price_prev=50000,
            price_delta_pct=30.0,
            is_anomaly=True,
            anomaly_z_score=3.5,
        )
        assert rec.price_condition == "Melampaui Ambang"
        assert rec.risk_level in ("tinggi", "kritis")
        # Should have HET-related fact
        het_facts = [
            f for f in rec.observed_facts
            if "HET" in f.label
        ]
        assert len(het_facts) > 0

    def test_build_with_extreme_weather(self):
        rec = build_recommendation(
            commodity_key="bawang_putih_test",
            commodity_name="Bawang Putih Test",
            province="DKI Jakarta",
            province_id=13,
            price_now=50000,
            has_extreme_weather=True,
            weather_detail="Curah hujan >100mm terdeteksi",
        )
        weather_factors = [
            f for f in rec.possible_factors
            if "Cuaca" in f.label
        ]
        assert len(weather_factors) > 0

    def test_build_with_near_holiday(self):
        rec = build_recommendation(
            commodity_key="cabai_rawit_test",
            commodity_name="Cabai Rawit Test",
            province="Sulawesi Selatan",
            province_id=26,
            price_now=75000,
            near_holiday=True,
            holiday_name="Idul Adha",
        )
        holiday_factors = [
            f for f in rec.possible_factors
            if "Hari Besar" in f.label
        ]
        assert len(holiday_factors) > 0

    def test_build_anomaly_signal_no_breach(self):
        rec = build_recommendation(
            commodity_key="normal_test",
            commodity_name="Normal Commodity",
            province="Banten",
            province_id=11,
            het_pct=50.0,
            het_status="aman",
            price_now=20000,
            price_prev=19500,
            price_delta_pct=2.5,
            is_anomaly=False,
        )
        assert rec.risk_level in ("rendah", "sedang")
        assert rec.price_condition == "Di Bawah Ambang"

    def test_recommendation_has_evidence_groups(self):
        rec = build_recommendation(
            commodity_key="cabai_rawit_merah",
            commodity_name="Cabai Rawit Merah",
            province="Jawa Barat",
            province_id=12,
            het_pct=95.0,
            het_status="kritis",
            price_now=65000,
            price_prev=55000,
            price_delta_pct=18.0,
            is_anomaly=True,
            anomaly_z_score=2.5,
            has_extreme_weather=True,
            weather_detail="Banjir di area produksi",
            rca_diagnosis="supply",
            rca_severity="L3",
        )
        # Verify all evidence groups exist
        assert len(rec.observed_facts) >= 2
        assert len(rec.possible_factors) > 0
        assert len(rec.missing_information) > 0
        assert len(rec.sources) >= 1
        assert len(rec.response_options) > 0
        assert rec.next_step is not None

    def test_price_condition_mapping(self):
        assert _map_het_to_price_condition(None) == "Tidak Tersedia"
        assert _map_het_to_price_condition(50.0) == "Di Bawah Ambang"
        assert _map_het_to_price_condition(85.0) == "Mendekati Ambang"
        assert _map_het_to_price_condition(110.0) == "Melampaui Ambang"

    def test_risk_level_mapping(self):
        assert _map_het_to_risk_level(50, False, False) == "rendah"
        assert _map_het_to_risk_level(110, False, False) == "tinggi"
        assert _map_het_to_risk_level(110, True, True) == "kritis"


# ── Graceful degradation tests ───────────────────────────────────────────────

class TestGracefulDegradation:
    """Verify the system degrades gracefully when signals are missing."""

    def test_recommendation_works_without_ml_forecast(self):
        """Build recommendation with no ML data — should still produce valid output."""
        rec = build_recommendation(
            commodity_key="test",
            commodity_name="Test Komoditas",
            province="Banten",
            province_id=11,
            price_now=30000,
            price_prev=28000,
            # No forecast_p50, forecast_p90, model_version
        )
        assert rec.knowledge_status == KnowledgeStatus.FACT
        assert len(rec.model_outputs) == 0
        assert "Forecast ML tidak tersedia" in rec.missing_information

    def test_recommendation_handles_zero_prices(self):
        """Edge case: price data is 0 (missing)."""
        rec = build_recommendation(
            commodity_key="test",
            commodity_name="Test",
            province="Banten",
            province_id=11,
            price_now=0,
            price_prev=0,
        )
        # Should still produce a valid recommendation with fallback
        assert rec.risk_level in ("rendah", "sedang")
        # Price fact shows "Tidak tersedia" for zero price
        price_facts = [
            f for f in rec.observed_facts
            if "Harga Saat Ini" in f.label
        ]
        assert len(price_facts) > 0

    def test_low_confidence_limits_response(self):
        """When confidence is low, response should be conservative."""
        rec = build_recommendation(
            commodity_key="test",
            commodity_name="Test",
            province="Banten",
            province_id=11,
            het_pct=120.0,
            het_status="melampaui",
            price_now=80000,
            is_anomaly=True,
            data_age_days=5.0,  # very stale
            coverage_ratio=0.3,  # low coverage
            history_days=30,     # insufficient history
        )
        assert rec.confidence_level == "low"
        # Should not have Koordinasikan or Intervensi
        response_types = [o.type for o in rec.response_options]
        assert ResponseType.PERTIMBANGKAN_INTERVENSI not in response_types
        assert ResponseType.KOORDINASIKAN not in response_types


# ── Confidence factor calculation edge cases ─────────────────────────────────

class TestConfidenceCalculation:
    """Test confidence factor boundary conditions."""

    def test_perfect_confidence(self):
        signals = ConfidenceSignals(
            freshness=1.0,
            coverage=1.0,
            history=1.0,
            model_performance=1.0,
        )
        factor, level = calculate_confidence_factor(signals)
        assert factor == 1.0
        assert level == "high"

    def test_threshold_high_boundary(self):
        signals = ConfidenceSignals(
            freshness=0.80,
            coverage=0.80,
            history=0.80,
            model_performance=0.80,
        )
        factor, level = calculate_confidence_factor(signals)
        assert factor == 0.80
        assert level == "high"

    def test_threshold_medium_boundary(self):
        signals = ConfidenceSignals(
            freshness=0.55,
            coverage=0.55,
            history=0.55,
            model_performance=0.55,
        )
        factor, level = calculate_confidence_factor(signals)
        assert factor == 0.55
        assert level == "medium"

    def test_threshold_low_boundary(self):
        signals = ConfidenceSignals(
            freshness=0.54,
            coverage=0.54,
            history=0.54,
            model_performance=0.54,
        )
        factor, level = calculate_confidence_factor(signals)
        assert factor == 0.54
        assert level == "low"

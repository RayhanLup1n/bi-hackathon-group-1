import pytest
from pydantic import ValidationError

from src.domain.schemas.decision import (
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


def test_priority_score_uses_prd_weights():
    signals = PrioritySignals(
        price_position=1.0,
        forecast_p90_breach=0.5,
        momentum_anomaly=0.0,
        regional_spread=0.0,
        weather_calendar=0.0,
    )

    assert calculate_priority_score(signals) == 40.0


def test_confidence_factor_and_level_use_weighted_components():
    signals = ConfidenceSignals(
        freshness=1.0,
        coverage=0.8,
        history=0.6,
        model_performance=0.4,
    )

    factor, level = calculate_confidence_factor(signals)

    assert factor == 0.72
    assert level == "medium"


def test_recommendation_display_score_is_reduced_by_confidence():
    recommendation = Recommendation(
        recommendation_id="rec-001",
        commodity="Cabai Merah",
        region="Banten",
        price_condition="Di atas ambang",
        risk_level="high",
        time_horizon_days=7,
        priority_signals=PrioritySignals(
            price_position=1.0,
            forecast_p90_breach=1.0,
            momentum_anomaly=1.0,
            regional_spread=1.0,
            weather_calendar=1.0,
        ),
        confidence_signals=ConfidenceSignals(
            freshness=0.5,
            coverage=0.5,
            history=0.5,
            model_performance=0.5,
        ),
        observed_facts=[
            EvidenceItem(
                kind=EvidenceKind.FACT,
                label="Harga harian",
                value="Naik 12%",
            )
        ],
        response_options=[
            ResponseOption(
                type=ResponseType.VERIFIKASI,
                label="Verifikasi pasokan lokal",
            )
        ],
        sources=[
            SourceReference(name="Serving price mart", cutoff="2026-07-12")
        ],
        knowledge_status=KnowledgeStatus.MODEL_OUTPUT,
    )

    assert recommendation.raw_priority_score == 100.0
    assert recommendation.confidence_factor == 0.5
    assert recommendation.confidence_level == "low"
    assert recommendation.display_priority_score == 50.0
    assert recommendation.requires_human_review is True


def test_signal_values_outside_normalized_range_are_rejected():
    with pytest.raises(ValidationError):
        PrioritySignals(
            price_position=1.1,
            forecast_p90_breach=0.0,
            momentum_anomaly=0.0,
            regional_spread=0.0,
            weather_calendar=0.0,
        )


def test_recommendation_preserves_evidence_groups():
    recommendation = Recommendation(
        recommendation_id="rec-002",
        commodity="Bawang Merah",
        region="Jawa Barat",
        price_condition="Normal",
        risk_level="low",
        time_horizon_days=14,
        priority_signals=PrioritySignals(),
        confidence_signals=ConfidenceSignals(),
        possible_factors=[
            EvidenceItem(
                kind=EvidenceKind.POSSIBLE_FACTOR,
                label="Cuaca",
                value="Hujan meningkat",
            )
        ],
        missing_information=["Data stok pasar tradisional"],
        sources=[
            SourceReference(name="Weather mart", cutoff="2026-07-12")
        ],
        knowledge_status=KnowledgeStatus.INFERENCE,
    )

    assert len(recommendation.possible_factors) == 1
    assert recommendation.missing_information == ["Data stok pasar tradisional"]
    assert recommendation.requires_human_review is True

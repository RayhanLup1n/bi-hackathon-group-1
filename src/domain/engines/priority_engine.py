"""
Priority Engine — aggregate signals from existing engines into a unified
Recommendation object for the decision-support workflow.

Inputs (from existing engines):
  - HET status (het_monitor)
  - RCA analysis (rca_engine)
  - Weather context (weather_data)
  - ML forecast/alert (optional, from ml_routes proxy)

Output:
  - Recommendation with priority score, confidence, evidence, and response options.

Design principle: pure domain logic. Data fetching happens in the application
orchestration layer; this engine only assembles and scores.

PRD Reference: Section 12 — Prioritization Engine.
"""
from __future__ import annotations

from datetime import date, datetime

from src.domain.schemas.decision import (
    ConfidenceLevel,
    ConfidenceSignals,
    EvidenceItem,
    EvidenceKind,
    KnowledgeStatus,
    PrioritySignals,
    Recommendation,
    ResponseOption,
    SourceReference,
    calculate_confidence_factor,
    calculate_priority_score,
)
from src.domain.engines.response_rules import get_next_step, get_response_options


def _build_recommendation_id(
    commodity_key: str,
    province: str,
    today: date | None = None,
) -> str:
    """Generate a stable recommendation_id.

    Format: rec_{date}_{commodity}_{province_hash}
    """
    ref_date = today or date.today()
    return f"rec_{ref_date.isoformat()}_{commodity_key}_{province.replace(' ', '_').lower()}"


def _map_het_to_price_condition(het_pct: float | None) -> str:
    """Map HET percentage to PRD price condition taxonomy."""
    if het_pct is None:
        return "Tidak Tersedia"
    if het_pct > 100:
        return "Melampaui Ambang"
    if het_pct >= 80:
        return "Mendekati Ambang"
    return "Di Bawah Ambang"


def _map_het_to_risk_level(
    het_pct: float | None,
    is_anomaly: bool,
    forecast_breach: bool = False,
) -> str:
    """Map combined signals to PRD risk taxonomy: rendah/sedang/tinggi/kritis."""
    signals = 0

    # HET signal
    if het_pct is not None:
        if het_pct > 100:
            signals += 3
        elif het_pct >= 80:
            signals += 2
        elif het_pct >= 60:
            signals += 1

    # Anomaly signal
    if is_anomaly:
        signals += 1

    # Forecast breach signal
    if forecast_breach:
        signals += 2

    if signals >= 4:
        return "kritis"
    if signals >= 3:
        return "tinggi"
    if signals >= 2:
        return "sedang"
    return "rendah"


def _normalize_signal(value: float, max_value: float, invert: bool = False) -> float:
    """Normalize a raw value to 0..1 range.

    Args:
        value: Raw signal value.
        max_value: Maximum expected value (maps to 1.0).
        invert: If True, higher raw values produce lower normalized signals.
    """
    if max_value <= 0:
        return 0.0
    normalized = min(1.0, max(0.0, value / max_value))
    return round(1.0 - normalized, 2) if invert else round(normalized, 2)


def build_recommendation(
    *,
    commodity_key: str,
    commodity_name: str,
    province: str,
    province_id: int,
    # HET signals
    het_pct: float | None = None,
    het_status: str = "",
    # Price signals
    price_now: int = 0,
    price_prev: int = 0,
    price_delta_pct: float = 0.0,
    # Anomaly signals
    is_anomaly: bool = False,
    anomaly_z_score: float = 0.0,
    # Regional spread (fraction of cities with rising prices)
    cities_total: int = 0,
    cities_rising: int = 0,
    # Weather/calendar signals
    has_extreme_weather: bool = False,
    weather_detail: str = "",
    near_holiday: bool = False,
    holiday_name: str = "",
    # Forecast (optional — ML may be offline)
    forecast_breach: bool = False,
    forecast_p90: float | None = None,
    forecast_p50: float | None = None,
    forecast_horizon: int = 7,
    model_version: str = "",
    model_wape: float | None = None,
    model_worse_than_baseline: bool = False,
    # Data quality
    data_age_days: float = 1.0,
    coverage_ratio: float = 1.0,
    history_days: int = 90,
    # RCA
    rca_diagnosis: str = "",
    rca_severity: str = "L0",
    rca_indicators: list[str] | None = None,
    # Date
    today: date | None = None,
) -> Recommendation:
    """Build a complete Recommendation from raw signals.

    This is the main entry point. The application orchestration layer gathers
    all inputs and passes them here. This function:
      1. Normalizes all signals to 0..1
      2. Computes priority score
      3. Computes confidence factor
      4. Maps risk level and price condition
      5. Builds evidence items
      6. Determines response options
    """
    ref_date = today or date.today()
    rec_id = _build_recommendation_id(commodity_key, province, ref_date)

    # ── Price condition & risk level ──────────────────────────────────────
    price_condition = _map_het_to_price_condition(het_pct)
    risk_level = _map_het_to_risk_level(het_pct, is_anomaly, forecast_breach)

    # ── Normalize priority signals 0..1 ───────────────────────────────────
    price_position = _normalize_signal(het_pct or 0, 120.0)  # 120% HET = max
    forecast_breach_signal = 1.0 if forecast_breach else 0.0
    momentum_signal = _normalize_signal(
        abs(anomaly_z_score) if anomaly_z_score else abs(price_delta_pct), 10.0
    )
    regional_spread = (
        cities_rising / cities_total if cities_total > 0 else 0.0
    )
    weather_calendar = 0.0
    if has_extreme_weather:
        weather_calendar += 0.5
    if near_holiday:
        weather_calendar += 0.5
    weather_calendar = min(1.0, weather_calendar)

    priority_signals = PrioritySignals(
        price_position=price_position,
        forecast_p90_breach=forecast_breach_signal,
        momentum_anomaly=momentum_signal,
        regional_spread=regional_spread,
        weather_calendar=weather_calendar,
    )

    # ── Confidence signals ────────────────────────────────────────────────
    from src.domain.engines.confidence_gate import build_confidence_signals

    confidence_signals = build_confidence_signals(
        data_age_days=data_age_days,
        coverage_ratio=coverage_ratio,
        history_days=history_days,
        wape=model_wape,
        is_worse_than_baseline=model_worse_than_baseline,
    )

    # ── Evidence: observed facts ──────────────────────────────────────────
    observed_facts: list[EvidenceItem] = []
    if het_pct is not None:
        observed_facts.append(EvidenceItem(
            kind=EvidenceKind.FACT,
            label="Posisi Harga vs HET",
            value=f"Harga {het_pct:.0f}% dari HET — {het_status}",
        ))
    if price_delta_pct != 0:
        direction = "naik" if price_delta_pct > 0 else "turun"
        observed_facts.append(EvidenceItem(
            kind=EvidenceKind.FACT,
            label="Perubahan Harga",
            value=f"Harga {direction} {abs(price_delta_pct):.1f}% dalam 7 hari",
        ))
    observed_facts.append(EvidenceItem(
        kind=EvidenceKind.FACT,
        label="Harga Saat Ini",
        value=f"Rp {price_now:,.0f}" if price_now > 0 else "Tidak tersedia",
    ))
    if cities_rising > 0:
        observed_facts.append(EvidenceItem(
            kind=EvidenceKind.FACT,
            label="Persebaran Kenaikan",
            value=f"{cities_rising}/{cities_total} kota mengalami kenaikan",
        ))

    # ── Evidence: model outputs ───────────────────────────────────────────
    model_outputs: list[EvidenceItem] = []
    if forecast_p50 is not None and forecast_p90 is not None:
        model_outputs.append(EvidenceItem(
            kind=EvidenceKind.MODEL_OUTPUT,
            label=f"Forecast P50 ({forecast_horizon} hari)",
            value=f"Rp {forecast_p50:,.0f}",
        ))
        model_outputs.append(EvidenceItem(
            kind=EvidenceKind.MODEL_OUTPUT,
            label=f"Forecast P90 ({forecast_horizon} hari)",
            value=f"Rp {forecast_p90:,.0f}",
        ))
    if forecast_breach:
        model_outputs.append(EvidenceItem(
            kind=EvidenceKind.MODEL_OUTPUT,
            label="Risiko Forecast",
            value="Forecast P90 melampaui ambang",
        ))

    # ── Evidence: possible factors ────────────────────────────────────────
    possible_factors: list[EvidenceItem] = []
    if has_extreme_weather:
        possible_factors.append(EvidenceItem(
            kind=EvidenceKind.POSSIBLE_FACTOR,
            label="Cuaca Ekstrem",
            value=weather_detail or "Cuaca ekstrem terdeteksi di wilayah",
        ))
    if near_holiday:
        possible_factors.append(EvidenceItem(
            kind=EvidenceKind.POSSIBLE_FACTOR,
            label="Hari Besar",
            value=holiday_name or "Mendekati hari besar",
        ))
    if rca_diagnosis and rca_diagnosis != "unknown":
        possible_factors.append(EvidenceItem(
            kind=EvidenceKind.POSSIBLE_FACTOR,
            label="Diagnosis RCA",
            value=rca_diagnosis,
        ))
    if is_anomaly:
        possible_factors.append(EvidenceItem(
            kind=EvidenceKind.POSSIBLE_FACTOR,
            label="Anomali Harga",
            value=f"Terjadi perubahan tidak biasa (z-score anomali)",
        ))

    # ── Missing information ───────────────────────────────────────────────
    missing_information: list[str] = []
    if model_wape is None:
        missing_information.append("Metrik performa model (WAPE) - ML server offline")
    if not forecast_breach and forecast_p50 is None:
        missing_information.append("Forecast ML - ML server offline")
    # Permanent data gaps (no data source available)
    missing_information.append("Kapasitas logistik (data tidak tersedia)")

    # ── Sources ───────────────────────────────────────────────────────────
    sources: list[SourceReference] = [
        SourceReference(
            name="PIHPS",
            cutoff=ref_date.isoformat(),
        ),
    ]
    if model_version:
        sources.append(SourceReference(
            name="LightGBM Forecast",
            cutoff=ref_date.isoformat(),
            model_version=model_version,
        ))

    # ── Confidence and scoring ────────────────────────────────────────────
    confidence_factor, confidence_level = calculate_confidence_factor(confidence_signals)

    # ── Response options ──────────────────────────────────────────────────
    response_options = get_response_options(risk_level, confidence_level)
    next_step = get_next_step(risk_level, confidence_level)

    # ── Knowledge status ──────────────────────────────────────────────────
    knowledge_status = KnowledgeStatus.MODEL_OUTPUT if forecast_p50 is not None else KnowledgeStatus.FACT

    # ── Assemble recommendation ───────────────────────────────────────────
    recommendation = Recommendation(
        recommendation_id=rec_id,
        commodity=commodity_name,
        region=province,
        price_condition=price_condition,
        risk_level=risk_level,
        time_horizon_days=forecast_horizon,
        priority_signals=priority_signals,
        confidence_signals=confidence_signals,
        observed_facts=observed_facts,
        model_outputs=model_outputs,
        possible_factors=possible_factors,
        next_step=next_step,
        response_options=response_options,
        missing_information=missing_information,
        sources=sources,
        knowledge_status=knowledge_status,
    )

    return recommendation

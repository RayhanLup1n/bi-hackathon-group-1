"""
Confidence Gate — compute confidence signals from data quality indicators.

Converts raw operational metrics (freshness days, coverage ratio, etc.) into
normalized ConfidenceSignals (0..1) that feed into the priority engine.

Pure functions — no database, network, or framework dependencies.

PRD Reference: Section 12.4 — Confidence factor based on:
  freshness (30%), coverage (25%), history (20%), model_performance (25%).
"""
from __future__ import annotations

from src.domain.schemas.decision import ConfidenceLevel, ConfidenceSignals


def compute_freshness_signal(data_age_days: float) -> float:
    """Convert data age in days to a freshness signal (0..1).

    0 days old → 1.0 (perfectly fresh)
    1 day  old → 0.9
    2 days old → 0.7
    3 days old → 0.5
    5+ days  → 0.1 (very stale)

    Uses exponential decay for smooth degradation.
    """
    if data_age_days < 0:
        data_age_days = 0.0
    # Exponential decay: e^(-0.4 * days)
    import math
    signal = math.exp(-0.4 * data_age_days)
    return round(max(0.0, min(1.0, signal)), 2)


def compute_coverage_signal(coverage_ratio: float) -> float:
    """Convert coverage ratio (0..1) directly to signal.

    1.0 (100% coverage) → 1.0
    0.75 → 0.75
    0.5  → 0.5

    Clamped to 0..1.
    """
    return round(max(0.0, min(1.0, coverage_ratio)), 2)


def compute_history_signal(min_days_required: int, available_days: int) -> float:
    """Compute history sufficiency signal.

    We need at least `min_days_required` (default 90) days of history for
    reliable forecasting. Less history → lower signal.

    Returns 0..1 where 1.0 = at least min_days_required days available.
    """
    if min_days_required <= 0:
        min_days_required = 90
    ratio = min(1.0, available_days / min_days_required)
    return round(ratio, 2)


def compute_model_performance_signal(
    wape: float | None = None,
    is_worse_than_baseline: bool = False,
) -> float:
    """Compute model performance signal.

    0..1 where:
      1.0 = model significantly better than baseline
      0.5 = model on par with baseline
      0.2 = model worse than baseline or no metrics available
      0.0 = model known to underperform, disabled

    Args:
        wape: WAPE percentage (e.g. 5.0 = 5%). Lower is better. None = unknown.
        is_worse_than_baseline: True if model performs worse than naive baseline.
    """
    if is_worse_than_baseline:
        return 0.2
    if wape is None:
        return 0.5  # unknown — neutral
    if wape <= 3.0:
        return 0.95
    if wape <= 5.0:
        return 0.85
    if wape <= 10.0:
        return 0.70
    if wape <= 15.0:
        return 0.55
    if wape <= 20.0:
        return 0.40
    return 0.25


def build_confidence_signals(
    data_age_days: float = 1.0,
    coverage_ratio: float = 1.0,
    history_days: int = 90,
    min_history_days: int = 90,
    wape: float | None = None,
    is_worse_than_baseline: bool = False,
) -> ConfidenceSignals:
    """Build a ConfidenceSignals object from raw operational metrics.

    Args:
        data_age_days: How many days since the latest data point.
        coverage_ratio: Fraction of expected cities/regions with data (0..1).
        history_days: How many days of historical data are available.
        min_history_days: Minimum days required for reliable analysis.
        wape: WAPE percentage (optional).
        is_worse_than_baseline: True if model underperforms baseline.

    Returns:
        ConfidenceSignals with normalized 0..1 values.
    """
    return ConfidenceSignals(
        freshness=compute_freshness_signal(data_age_days),
        coverage=compute_coverage_signal(coverage_ratio),
        history=compute_history_signal(min_history_days, history_days),
        model_performance=compute_model_performance_signal(
            wape=wape,
            is_worse_than_baseline=is_worse_than_baseline,
        ),
    )


def is_confidence_too_low(level: ConfidenceLevel) -> bool:
    """Shortcut: check if confidence is too low for specific recommendations."""
    return level == "low"

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceKind(str, Enum):
    FACT = "fact"
    MODEL_OUTPUT = "model_output"
    POSSIBLE_FACTOR = "possible_factor"
    MISSING_INFORMATION = "missing_information"


class KnowledgeStatus(str, Enum):
    FACT = "fact"
    MODEL_OUTPUT = "model_output"
    INFERENCE = "inference"
    SIMULATION = "simulation"


class ResponseType(str, Enum):
    MONITOR = "Monitor"
    VERIFIKASI = "Verifikasi"
    KOORDINASIKAN = "Koordinasikan"
    PERTIMBANGKAN_INTERVENSI = "Pertimbangkan Intervensi"


ConfidenceLevel = Literal["high", "medium", "low"]


class SourceReference(BaseModel):
    name: str
    cutoff: str
    url: str | None = None
    model_version: str | None = None

    @field_validator("name", "cutoff")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class EvidenceItem(BaseModel):
    kind: EvidenceKind
    label: str
    value: str
    source_ref: str | None = None

    @field_validator("label", "value")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class ResponseOption(BaseModel):
    type: ResponseType
    label: str
    description: str | None = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label must not be empty")
        return value


class PrioritySignals(BaseModel):
    price_position: float = Field(default=0.0, ge=0.0, le=1.0)
    forecast_p90_breach: float = Field(default=0.0, ge=0.0, le=1.0)
    momentum_anomaly: float = Field(default=0.0, ge=0.0, le=1.0)
    regional_spread: float = Field(default=0.0, ge=0.0, le=1.0)
    weather_calendar: float = Field(default=0.0, ge=0.0, le=1.0)


class ConfidenceSignals(BaseModel):
    freshness: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    history: float = Field(default=0.0, ge=0.0, le=1.0)
    model_performance: float = Field(default=0.0, ge=0.0, le=1.0)


PRIORITY_WEIGHTS = {
    "price_position": 0.25,
    "forecast_p90_breach": 0.30,
    "momentum_anomaly": 0.20,
    "regional_spread": 0.15,
    "weather_calendar": 0.10,
}

CONFIDENCE_WEIGHTS = {
    "freshness": 0.30,
    "coverage": 0.25,
    "history": 0.20,
    "model_performance": 0.25,
}


def calculate_priority_score(signals: PrioritySignals) -> float:
    weighted_score = sum(
        getattr(signals, field_name) * weight
        for field_name, weight in PRIORITY_WEIGHTS.items()
    )
    return round(weighted_score * 100, 2)


def calculate_confidence_factor(
    signals: ConfidenceSignals,
) -> tuple[float, ConfidenceLevel]:
    factor = round(
        sum(
            getattr(signals, field_name) * weight
            for field_name, weight in CONFIDENCE_WEIGHTS.items()
        ),
        2,
    )
    level: ConfidenceLevel = (
        "high" if factor >= 0.80 else "medium" if factor >= 0.55 else "low"
    )
    return factor, level


class Recommendation(BaseModel):
    recommendation_id: str
    commodity: str
    region: str
    price_condition: str
    risk_level: str
    time_horizon_days: int = Field(gt=0)
    priority_signals: PrioritySignals
    confidence_signals: ConfidenceSignals
    observed_facts: list[EvidenceItem] = Field(default_factory=list)
    model_outputs: list[EvidenceItem] = Field(default_factory=list)
    possible_factors: list[EvidenceItem] = Field(default_factory=list)
    next_step: str | None = None
    response_options: list[ResponseOption] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    knowledge_status: KnowledgeStatus
    requires_human_review: Literal[True] = True
    raw_priority_score: float = 0.0
    confidence_factor: float = 0.0
    confidence_level: ConfidenceLevel = "low"
    display_priority_score: float = 0.0

    @field_validator(
        "recommendation_id",
        "commodity",
        "region",
        "price_condition",
        "risk_level",
    )
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("missing_information")
    @classmethod
    def validate_missing_information(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("missing information values must not be empty")
        return values

    @model_validator(mode="after")
    def calculate_scores(self) -> "Recommendation":
        self.raw_priority_score = calculate_priority_score(self.priority_signals)
        self.confidence_factor, self.confidence_level = calculate_confidence_factor(
            self.confidence_signals
        )
        self.display_priority_score = round(
            self.raw_priority_score * self.confidence_factor,
            2,
        )
        return self


class BundleCommodity(BaseModel):
    """A single commodity entry inside a review bundle."""

    recommendation_id: str
    name: str
    risk_level: str
    display_priority_score: float

    @field_validator("recommendation_id", "name", "risk_level")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class Bundle(BaseModel):
    """A review bundle grouping related recommendations for coordinated review."""

    bundle_id: str
    name: str
    reason: str
    bundle_type: str  # risk_cluster | commodity_family | confidence_gap
    commodities: list[BundleCommodity] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    priority_score: float = 0.0

    @field_validator("bundle_id", "name", "reason", "bundle_type")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("missing_information")
    @classmethod
    def validate_missing_info(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("missing information values must not be empty")
        return values

"""
Input validation guardrails — reusable validation functions for API routes.

Validates: commodity keys, province names, pagination params, date ranges.
Pure functions — no DB, no HTTP deps.
"""
from __future__ import annotations

import re

# Known valid MVP values (keeps routes DRY)
VALID_PROVINCES: frozenset[str] = frozenset({
    "Banten", "Jawa Barat", "DKI Jakarta", "Sulawesi Selatan", "Nasional",
})

VALID_RISK_LEVELS: frozenset[str] = frozenset({
    "rendah", "sedang", "tinggi", "kritis",
})

VALID_REVIEW_STATUSES: frozenset[str] = frozenset({
    "Belum Ditinjau", "Untuk Dibahas", "Ditunda", "Ditolak",
})

VALID_EXPORT_FORMATS: frozenset[str] = frozenset({"csv", "xlsx"})

# Commodity keys: alphanumeric + underscore, max 64 chars
_COMMODITY_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+$")
MAX_KEY_LENGTH = 64


def validate_commodity_key(key: str) -> str:
    """Validate and sanitize a commodity key.

    Rejects path traversal, special chars, empty strings.

    Returns:
        The validated key (stripped).

    Raises:
        ValueError: If key is invalid.
    """
    key = key.strip()
    if not key:
        raise ValueError("Commodity key must not be empty")
    if len(key) > MAX_KEY_LENGTH:
        raise ValueError(f"Commodity key too long (max {MAX_KEY_LENGTH} chars)")
    if not _COMMODITY_KEY_RE.match(key):
        raise ValueError(
            "Commodity key must only contain letters, numbers, and underscores"
        )
    if key.startswith((".", "/", "\\")):
        raise ValueError("Commodity key must not start with path separators")
    return key


def validate_province(province: str, *, allow_nasional: bool = True) -> str:
    """Validate province name against known MVP provinces.

    Args:
        province: Province name to validate.
        allow_nasional: If True, "Nasional" is also valid.

    Returns:
        Validated province name.

    Raises:
        ValueError: If province is not recognized.
    """
    province = province.strip()
    valid = set(VALID_PROVINCES)
    if not allow_nasional:
        valid.discard("Nasional")
    if province not in valid:
        raise ValueError(
            f"Unknown province: {province!r}. "
            f"Valid: {', '.join(sorted(valid))}"
        )
    return province


def validate_risk_level(risk: str) -> str:
    """Validate risk level filter value."""
    risk = risk.strip().lower()
    if risk not in VALID_RISK_LEVELS:
        raise ValueError(
            f"Unknown risk level: {risk!r}. "
            f"Valid: {', '.join(sorted(VALID_RISK_LEVELS))}"
        )
    return risk


def pagination(limit: int, offset: int, *, max_limit: int = 100) -> tuple[int, int]:
    """Validate and normalize pagination params.

    Returns:
        (limit, offset) — both clamped to safe ranges.

    Raises:
        ValueError: If values are negative or limit exceeds max.
    """
    if offset < 0:
        raise ValueError("Offset must not be negative")
    if limit < 1:
        raise ValueError("Limit must be at least 1")
    if limit > max_limit:
        raise ValueError(f"Limit must not exceed {max_limit}")
    return (limit, offset)


def date_range(n_days: int, *, max_days: int = 365) -> int:
    """Validate a day count for lookback/range params."""
    if n_days < 1:
        raise ValueError("Day count must be at least 1")
    if n_days > max_days:
        raise ValueError(f"Day count must not exceed {max_days}")
    return n_days


def export_format(fmt: str) -> str:
    """Validate export format string."""
    fmt = fmt.strip().lower()
    if fmt not in VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Unknown export format: {fmt!r}. Valid: csv, xlsx"
        )
    return fmt


def review_status(status: str) -> str:
    """Validate review status value."""
    status = status.strip()
    if status not in VALID_REVIEW_STATUSES:
        raise ValueError(
            f"Unknown review status: {status!r}. "
            f"Valid: {', '.join(sorted(VALID_REVIEW_STATUSES))}"
        )
    return status

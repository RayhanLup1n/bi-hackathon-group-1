"""Unit tests for input validation guardrails."""
from __future__ import annotations

import pytest

from src.api.guardrails import (
    date_range,
    export_format,
    pagination,
    review_status,
    validate_commodity_key,
    validate_province,
    validate_risk_level,
)


class TestValidateCommodityKey:
    """Commodity key validation and sanitization."""

    def test_valid_keys_pass(self):
        for key in ["bawang_merah", "cabai_rawit_merah", "k123", "BAWANG_PUTIH"]:
            assert validate_commodity_key(key) == key

    def test_strips_whitespace(self):
        assert validate_commodity_key("  bawang_merah  ") == "bawang_merah"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_commodity_key("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_commodity_key("   ")

    def test_path_traversal_blocked(self):
        for key in ["../etc/passwd", "./config", "../../../secret"]:
            with pytest.raises(ValueError):
                validate_commodity_key(key)

    def test_special_chars_blocked(self):
        for key in ["bawang;drop", "key--inject", "foo bar", "x' OR '1"]:
            with pytest.raises(ValueError):
                validate_commodity_key(key)

    def test_excessively_long_key_raises(self):
        with pytest.raises(ValueError, match="too long"):
            validate_commodity_key("a" * 65)


class TestValidateProvince:
    """Province name validation."""

    def test_valid_provinces_pass(self):
        for p in ["Banten", "Jawa Barat", "DKI Jakarta", "Sulawesi Selatan", "Nasional"]:
            assert validate_province(p) == p

    def test_unknown_province_raises(self):
        with pytest.raises(ValueError, match="Unknown province"):
            validate_province("Bali")

    def test_nasional_allowed_by_default(self):
        assert validate_province("Nasional") == "Nasional"

    def test_nasional_blocked_when_flag_false(self):
        with pytest.raises(ValueError):
            validate_province("Nasional", allow_nasional=False)

    def test_strips_whitespace(self):
        assert validate_province("  DKI Jakarta  ") == "DKI Jakarta"


class TestValidateRiskLevel:
    """Risk level validation."""

    def test_valid_risk_levels(self):
        for r in ["rendah", "sedang", "tinggi", "kritis"]:
            assert validate_risk_level(r) == r

    def test_case_insensitive(self):
        assert validate_risk_level("KRITIS") == "kritis"

    def test_unknown_risk_raises(self):
        with pytest.raises(ValueError, match="Unknown risk level"):
            validate_risk_level("medium")


class TestPagination:
    """Pagination parameter validation."""

    def test_valid_pagination(self):
        limit, offset = pagination(20, 10)
        assert limit == 20
        assert offset == 10

    def test_negative_offset_raises(self):
        with pytest.raises(ValueError, match="Offset must not be negative"):
            pagination(10, -1)

    def test_zero_limit_raises(self):
        with pytest.raises(ValueError, match="Limit must be at least 1"):
            pagination(0, 0)

    def test_limit_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="Limit must not exceed"):
            pagination(200, 0, max_limit=100)

    def test_custom_max_limit(self):
        limit, offset = pagination(500, 0, max_limit=1000)
        assert limit == 500


class TestDateRange:
    """Date range validation."""

    def test_valid_range(self):
        assert date_range(30) == 30

    def test_negative_days_raises(self):
        with pytest.raises(ValueError, match="must be at least 1"):
            date_range(-1)

    def test_zero_days_raises(self):
        with pytest.raises(ValueError, match="must be at least 1"):
            date_range(0)

    def test_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="must not exceed"):
            date_range(400, max_days=365)


class TestExportFormat:
    """Export format validation."""

    def test_valid_formats(self):
        for f in ["csv", "xlsx", "CSV", "XLSX"]:
            assert export_format(f) in ("csv", "xlsx")

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown export format"):
            export_format("pdf")


class TestReviewStatus:
    """Review status validation."""

    def test_valid_statuses(self):
        for s in ["Belum Ditinjau", "Untuk Dibahas", "Ditunda", "Ditolak"]:
            assert review_status(s) == s

    def test_unknown_status_raises(self):
        with pytest.raises(ValueError, match="Unknown review status"):
            review_status("Approved")

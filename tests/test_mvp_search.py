"""
Unit tests for mvp_search.py — keyword search across recommendations.

All tests use hardcoded dict fixtures matching Recommendation.model_dump() output.
No database, no HTTP — pure function tests.
"""
from __future__ import annotations

import pytest
from src.application.mvp_search import search_recommendations


# ── Test fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_priorities() -> list[dict]:
    """Minimal recommendation dicts matching the priority engine output shape."""
    return [
        {
            "recommendation_id": "rec_bawang_merah_banten",
            "commodity": "Bawang Merah",
            "region": "Nasional",
            "price_condition": "Di Bawah Ambang",
            "risk_level": "sedang",
            "display_priority_score": 45.0,
            "raw_priority_score": 60.0,
            "confidence_factor": 0.75,
            "confidence_level": "medium",
            "time_horizon_days": 7,
            "next_step": "Monitor harga bawang merah secara berkala",
            "knowledge_status": "FACT",
            "observed_facts": [
                {"kind": "FACT", "label": "HET saat ini", "value": "75%"},
                {"kind": "FACT", "label": "Harga Saat Ini", "value": "Rp 30,000/kg"},
            ],
            "model_outputs": [],
            "possible_factors": [],
            "missing_information": ["Data stok bawang merah tidak tersedia"],
            "response_options": [],
            "sources": [],
        },
        {
            "recommendation_id": "rec_cabai_rawit_jabar",
            "commodity": "Cabai Rawit Merah",
            "region": "Nasional",
            "price_condition": "Melampaui Ambang",
            "risk_level": "kritis",
            "display_priority_score": 92.5,
            "raw_priority_score": 98.0,
            "confidence_factor": 0.94,
            "confidence_level": "high",
            "time_horizon_days": 7,
            "next_step": "Verifikasi harga dan koordinasikan eskalsi",
            "knowledge_status": "MODEL_OUTPUT",
            "observed_facts": [
                {"kind": "FACT", "label": "HET cabai", "value": "130%"},
                {"kind": "FACT", "label": "Harga Saat Ini", "value": "Rp 85,000/kg"},
            ],
            "model_outputs": [
                {"kind": "MODEL_OUTPUT", "label": "Forecast P90", "value": "Rp 95,000"},
            ],
            "possible_factors": [
                {"kind": "POSSIBLE_FACTOR", "label": "Cuaca", "value": "Hujan ekstrem"},
            ],
            "missing_information": [
                "Data stok cabai tidak tersedia",
                "Volume distribusi tidak diketahui",
            ],
            "response_options": [],
            "sources": [],
        },
        {
            "recommendation_id": "rec_bawang_putih_dki",
            "commodity": "Bawang Putih",
            "region": "Nasional",
            "price_condition": "Mendekati Ambang",
            "risk_level": "tinggi",
            "display_priority_score": 67.0,
            "raw_priority_score": 78.0,
            "confidence_factor": 0.86,
            "confidence_level": "high",
            "time_horizon_days": 7,
            "next_step": "Verifikasi pasokan bawang putih",
            "knowledge_status": "FACT",
            "observed_facts": [
                {"kind": "FACT", "label": "HET bawang putih", "value": "90%"},
            ],
            "model_outputs": [],
            "possible_factors": [],
            "missing_information": ["Data impor bawang putih"],
            "response_options": [],
            "sources": [],
        },
    ]


# ── Search tests ─────────────────────────────────────────────────────────────

class TestSearchRecommendations:
    """Verify keyword search behavior."""

    def test_exact_commodity_match_returns_top_score(self, sample_priorities):
        # "Bawang Merah" tokens may also match "Bawang Putih" + "Cabai Rawit Merah"
        result = search_recommendations(sample_priorities, "Bawang Merah")
        assert result["total"] >= 1
        # Top result should be Bawang Merah (most matching tokens)
        assert result["results"][0]["commodity"] == "Bawang Merah"
        assert result["results"][0]["relevance_score"] >= 10

    def test_partial_commodity_match(self, sample_priorities):
        result = search_recommendations(sample_priorities, "cabai")
        assert result["total"] == 1
        assert result["results"][0]["commodity"] == "Cabai Rawit Merah"

    def test_search_matches_multiple_results(self, sample_priorities):
        result = search_recommendations(sample_priorities, "bawang")
        assert result["total"] == 2  # Bawang Merah + Bawang Putih

    def test_match_on_risk_level(self, sample_priorities):
        result = search_recommendations(sample_priorities, "kritis")
        assert result["total"] == 1
        assert result["results"][0]["risk_level"] == "kritis"

    def test_match_on_evidence_label(self, sample_priorities):
        result = search_recommendations(sample_priorities, "HET")
        # 3 recs have HET in evidence labels
        assert result["total"] >= 2

    def test_match_on_evidence_value(self, sample_priorities):
        result = search_recommendations(sample_priorities, "130%")
        assert result["total"] == 1
        assert result["results"][0]["commodity"] == "Cabai Rawit Merah"

    def test_match_on_missing_information(self, sample_priorities):
        result = search_recommendations(sample_priorities, "impor")
        assert result["total"] == 1
        assert result["results"][0]["commodity"] == "Bawang Putih"

    def test_match_on_price_condition(self, sample_priorities):
        result = search_recommendations(sample_priorities, "Melampaui")
        assert result["total"] == 1
        assert result["results"][0]["commodity"] == "Cabai Rawit Merah"

    def test_empty_query_returns_empty(self, sample_priorities):
        result = search_recommendations(sample_priorities, "")
        assert result["total"] == 0
        assert result["results"] == []

    def test_whitespace_query_returns_empty(self, sample_priorities):
        result = search_recommendations(sample_priorities, "   ")
        assert result["total"] == 0
        assert result["results"] == []

    def test_no_match_returns_empty(self, sample_priorities):
        result = search_recommendations(sample_priorities, "xyzabc_nonexistent")
        assert result["total"] == 0
        assert result["results"] == []

    def test_results_sorted_by_relevance_then_priority(self, sample_priorities):
        result = search_recommendations(sample_priorities, "bawang")
        assert result["total"] == 2
        # Both match "bawang" partially — check higher priority score first
        scores = [r["display_priority_score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_case_insensitive_match(self, sample_priorities):
        result_lower = search_recommendations(sample_priorities, "bawang merah")
        result_upper = search_recommendations(sample_priorities, "BAWANG MERAH")
        result_mixed = search_recommendations(sample_priorities, "BawAng mERah")
        # All should return the same result
        assert result_lower["total"] == result_upper["total"] == result_mixed["total"]

    def test_max_results_cap_at_20(self, sample_priorities):
        # Only 3 recs, so cap doesn't cut here — verify cap is passed through
        result = search_recommendations(sample_priorities, "bawang", max_results=1)
        assert len(result["results"]) == 1
        assert result["total"] == 2  # total before cap

    def test_offset_pagination(self, sample_priorities):
        result = search_recommendations(sample_priorities, "bawang", max_results=1, offset=0)
        all_results = search_recommendations(sample_priorities, "bawang")
        first = all_results["results"][0]
        second = all_results["results"][1]
        # offset=0 returns first
        assert result["results"][0]["commodity"] == first["commodity"]
        # offset=1 returns second
        result2 = search_recommendations(sample_priorities, "bawang", max_results=1, offset=1)
        assert result2["results"][0]["commodity"] == second["commodity"]
        assert result2["total"] == 2
        assert result2["offset"] == 1

    def test_offset_beyond_total_returns_empty(self, sample_priorities):
        result = search_recommendations(sample_priorities, "bawang", offset=10)
        assert result["total"] == 2
        assert result["results"] == []

    def test_single_character_query(self, sample_priorities):
        result = search_recommendations(sample_priorities, "a")
        # "a" appears in many fields — should match everything
        assert result["total"] == 3

    def test_results_have_required_fields(self, sample_priorities):
        result = search_recommendations(sample_priorities, "cabai")
        assert result["total"] >= 1
        r = result["results"][0]
        for field in (
            "recommendation_id", "commodity", "region", "risk_level",
            "display_priority_score", "relevance_score", "matched_terms",
        ):
            assert field in r, f"Missing field: {field}"

    def test_matched_terms_tracks_what_matched(self, sample_priorities):
        result = search_recommendations(sample_priorities, "cabai")
        assert result["total"] >= 1
        terms = result["results"][0]["matched_terms"]
        assert any("cabai" in t for t in terms)

    def test_risk_level_filtering_via_search(self, sample_priorities):
        result = search_recommendations(sample_priorities, "rendah")
        assert result["total"] == 0  # no 'rendah' items in fixture

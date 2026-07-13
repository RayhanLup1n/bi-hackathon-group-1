"""
Unit tests for mvp_bundles.py — review bundle generation.

Tests cover all three strategies: risk_cluster, commodity_family, confidence_gap.
No database, no HTTP — pure function tests with dict fixtures.
"""
from __future__ import annotations

import pytest

from src.application.mvp_bundles import generate_bundles, COMMODITY_FAMILIES


# ── Test fixtures ──────────────────────────────────────────────────────────

def _rec(
    rec_id: str,
    commodity: str,
    risk_level: str = "sedang",
    confidence_level: str = "medium",
    display_priority_score: float = 50.0,
    missing_information: list[str] | None = None,
) -> dict:
    """Factory for minimal recommendation dicts matching orchestrator output."""
    return {
        "recommendation_id": rec_id,
        "commodity": commodity,
        "region": "Nasional",
        "price_condition": "Di Bawah Ambang",
        "risk_level": risk_level,
        "display_priority_score": display_priority_score,
        "raw_priority_score": 60.0,
        "confidence_factor": 0.75,
        "confidence_level": confidence_level,
        "time_horizon_days": 7,
        "next_step": "Monitor",
        "knowledge_status": "FACT",
        "observed_facts": [],
        "model_outputs": [],
        "possible_factors": [],
        "missing_information": missing_information or ["Volume stok", "Kapasitas logistik"],
        "response_options": [],
        "sources": [{"name": "PIHPS", "cutoff": "2026-07-13"}],
        "priority_signals": {
            "price_position": 0.5, "forecast_p90_breach": 0.0,
            "momentum_anomaly": 0.3, "regional_spread": 0.2, "weather_calendar": 0.0,
        },
        "confidence_signals": {
            "freshness": 0.8, "coverage": 0.7, "history": 0.6, "model_performance": 0.5,
        },
    }


@pytest.fixture
def sample_recs() -> list[dict]:
    """6 recommendations: 1 kritis, 1 tinggi, 2 sedang (cabai family), 1 low conf, 1 rendah."""
    cabai_merah = _rec("rec_cabai_merah", "Cabai Merah Besar", "kritis", "high", 92.5)
    cabai_keriting = _rec("rec_cabai_keriting", "Cabai Merah Keriting", "tinggi", "medium", 72.0)
    cabai_rawit = _rec("rec_cabai_rawit_hijau", "Cabai Rawit Hijau", "sedang", "low", 45.0)
    bawang_merah = _rec("rec_bawang_merah", "Bawang Merah", "sedang", "medium", 48.0)
    bawang_putih = _rec("rec_bawang_putih", "Bawang Putih", "rendah", "high", 30.0)
    low_conf = _rec("rec_low_conf", "Cabai Rawit Merah", "sedang", "low", 40.0,
                    missing_information=["Metrik performa model (WAPE)", "Volume stok"])
    return [cabai_merah, cabai_keriting, cabai_rawit, bawang_merah, bawang_putih, low_conf]


@pytest.fixture
def single_rec() -> list[dict]:
    return [_rec("rec_solo", "Bawang Merah", "sedang", "high", 50.0)]


# ── Risk cluster tests ────────────────────────────────────────────────────

class TestRiskClusterBundles:
    """Verify risk_cluster strategy."""

    def test_generates_kritis_bundle(self, sample_recs):
        bundles = generate_bundles(sample_recs)
        kritis_bundles = [b for b in bundles if b["bundle_type"] == "risk_cluster" and "Kritis" in b["name"]]
        # Only 1 kritis rec => needs 2+ min => no kritis bundle
        assert len(kritis_bundles) == 0  # minimum 2 required

    def test_generates_kritis_bundle_with_two_members(self):
        recs = [
            _rec("r1", "Cabai Merah Besar", "kritis", "high", 95.0),
            _rec("r2", "Bawang Merah", "kritis", "high", 88.0),
        ]
        bundles = generate_bundles(recs)
        kritis = [b for b in bundles if b["bundle_type"] == "risk_cluster" and "Kritis" in b["name"]]
        assert len(kritis) == 1
        assert len(kritis[0]["commodities"]) == 2

    def test_generates_tinggi_bundle(self, sample_recs):
        bundles = generate_bundles(sample_recs)
        tinggi = [b for b in bundles if b["bundle_type"] == "risk_cluster" and "Tinggi" in b["name"]]
        # Only 1 tinggi rec => needs 2+ min
        assert len(tinggi) == 0

    def test_generates_tinggi_bundle_with_two_members(self):
        recs = [
            _rec("r1", "Cabai Merah Besar", "tinggi", "medium", 72.0),
            _rec("r2", "Bawang Merah", "tinggi", "medium", 68.0),
        ]
        bundles = generate_bundles(recs)
        tinggi = [b for b in bundles if b["bundle_type"] == "risk_cluster" and "Tinggi" in b["name"]]
        assert len(tinggi) == 1
        assert len(tinggi[0]["commodities"]) == 2

    def test_risk_cluster_skips_rendah_and_sedang(self):
        """Risk clusters only cover kritis and tinggi."""
        recs = [
            _rec("r1", "A", "rendah", "high", 10.0),
            _rec("r2", "B", "rendah", "medium", 15.0),
            _rec("r3", "C", "sedang", "high", 30.0),
            _rec("r4", "D", "sedang", "medium", 35.0),
        ]
        bundles = generate_bundles(recs)
        risk_clusters = [b for b in bundles if b["bundle_type"] == "risk_cluster"]
        assert len(risk_clusters) == 0

    def test_risk_cluster_sorts_by_score(self):
        recs = [
            _rec("r1", "A", "tinggi", "medium", 60.0),
            _rec("r2", "B", "tinggi", "medium", 90.0),
        ]
        bundles = generate_bundles(recs)
        cluster = [b for b in bundles if b["bundle_type"] == "risk_cluster"][0]
        assert cluster["priority_score"] == 75.0  # avg of 60 + 90


# ── Commodity family tests ─────────────────────────────────────────────────

class TestCommodityFamilyBundles:
    """Verify commodity_family strategy."""

    def test_generates_cabai_family(self, sample_recs):
        bundles = generate_bundles(sample_recs)
        cabai = [b for b in bundles if b["bundle_type"] == "commodity_family" and "Cabai" in b["name"]]
        assert len(cabai) == 1
        # 3 cabai recs: kritis/tinggi/sedang => all >= sedang => all 3 included
        # 4 cabai recs: all 4 are >= sedang (includes Cabai Rawit Merah from low_conf fixture)
        assert len(cabai[0]["commodities"]) == 4

    def test_cabai_family_excludes_rendah_members(self):
        """Commodity family only includes members with risk >= sedang."""
        recs = [
            _rec("r1", "Cabai Merah Besar", "tinggi", "high", 82.0),
            _rec("r2", "Cabai Merah Keriting", "rendah", "high", 20.0),
            _rec("r3", "Cabai Rawit Merah", "sedang", "medium", 45.0),
        ]
        bundles = generate_bundles(recs)
        cabai = [b for b in bundles if b["bundle_type"] == "commodity_family"][0]
        # Only r1 and r3 are >= sedang
        assert len(cabai["commodities"]) == 2
        names = [c["name"] for c in cabai["commodities"]]
        assert "Cabai Merah Besar" in names
        assert "Cabai Rawit Merah" in names
        assert "Cabai Merah Keriting" not in names

    def test_bawang_family_needs_two_eligible(self, sample_recs):
        """Bawang: Merah (sedang) + Putih (rendah) = only 1 eligible — skipped."""
        bundles = generate_bundles(sample_recs)
        bawang = [b for b in bundles if b["bundle_type"] == "commodity_family" and "Bawang" in b["name"]]
        # Bawang Putih is rendah (skipped), Bawang Merah is sedang => 1 eligible < 2
        assert len(bawang) == 0

    def test_bawang_family_with_two_eligible(self):
        recs = [
            _rec("r1", "Bawang Merah", "sedang", "medium", 48.0),
            _rec("r2", "Bawang Putih", "sedang", "medium", 45.0),
        ]
        bundles = generate_bundles(recs)
        bawang = [b for b in bundles if b["bundle_type"] == "commodity_family" and "Bawang" in b["name"]]
        assert len(bawang) == 1
        assert len(bawang[0]["commodities"]) == 2

    def test_family_reason_includes_highest_risk(self):
        recs = [
            _rec("r1", "Cabai Merah Besar", "kritis", "high", 95.0),
            _rec("r2", "Cabai Rawit Merah", "sedang", "medium", 45.0),
        ]
        bundles = generate_bundles(recs)
        cabai = [b for b in bundles if b["bundle_type"] == "commodity_family"][0]
        assert "kritis" in cabai["reason"]

    def test_family_skips_when_less_than_two(self):
        """When only 1 commodity from a family exists at >= sedang, no bundle."""
        recs = [
            _rec("r1", "Bawang Merah", "sedang", "medium", 48.0),
            _rec("r2", "Cabai Merah Besar", "rendah", "high", 15.0),
        ]
        bundles = generate_bundles(recs)
        family_bundles = [b for b in bundles if b["bundle_type"] == "commodity_family"]
        assert len(family_bundles) == 0


# ── Confidence gap tests ───────────────────────────────────────────────────

class TestConfidenceGapBundles:
    """Verify confidence_gap strategy."""

    def test_generates_confidence_gap(self, sample_recs):
        bundles = generate_bundles(sample_recs)
        gaps = [b for b in bundles if b["bundle_type"] == "confidence_gap"]
        assert len(gaps) == 1
        gap = gaps[0]
        # cabai_rawit_hijau (low) + rec_low_conf (low) = 2 low confidence recs
        assert len(gap["commodities"]) == 2

    def test_confidence_gap_allows_single_member(self):
        """Confidence gap allows min 1 member (unlike risk cluster's min 2)."""
        recs = [
            _rec("r1", "A", "sedang", "low", 40.0),
            _rec("r2", "B", "sedang", "high", 50.0),
        ]
        bundles = generate_bundles(recs)
        gaps = [b for b in bundles if b["bundle_type"] == "confidence_gap"]
        assert len(gaps) == 1
        assert len(gaps[0]["commodities"]) == 1

    def test_confidence_gap_excludes_medium_and_high(self):
        recs = [
            _rec("r1", "A", "kritis", "high", 90.0),
            _rec("r2", "B", "tinggi", "medium", 70.0),
        ]
        bundles = generate_bundles(recs)
        gaps = [b for b in bundles if b["bundle_type"] == "confidence_gap"]
        assert len(gaps) == 0


# ── Edge cases ─────────────────────────────────────────────────────────────

class TestBundleEdgeCases:
    """Verify edge case handling."""

    def test_empty_input(self):
        assert generate_bundles([]) == []

    def test_single_recommendation(self, single_rec):
        bundles = generate_bundles(single_rec)
        # single rec has medium confidence => no confidence_gap
        # Risk rendah => no risk cluster
        # 1 bawang merah alone => no commodity_family (need 2)
        assert len(bundles) == 0

    def test_all_rendah_no_bundles(self):
        recs = [
            _rec("r1", "A", "rendah", "high", 10.0),
            _rec("r2", "B", "rendah", "high", 15.0),
        ]
        bundles = generate_bundles(recs)
        assert len(bundles) == 0

    def test_duplicate_missing_info_deduplicated(self):
        recs = [
            _rec("r1", "A", "kritis", "high", 90.0, missing_information=["Volume stok"]),
            _rec("r2", "B", "kritis", "high", 88.0, missing_information=["Volume stok", "Metrik WAPE"]),
        ]
        bundles = generate_bundles(recs)
        kritis = [b for b in bundles if b["bundle_type"] == "risk_cluster"][0]
        missing = kritis["missing_information"]
        assert len(missing) == 2
        assert missing == ["Volume stok", "Metrik WAPE"]

    def test_bundles_sorted_by_priority_score_desc(self):
        recs = [
            _rec("r1", "A", "tinggi", "low", 30.0),
            _rec("r2", "B", "tinggi", "low", 50.0),
            _rec("r3", "C", "kritis", "low", 90.0),
            _rec("r4", "D", "kritis", "low", 70.0),
        ]
        bundles = generate_bundles(recs)
        # Risk clusters (kritis=80, tinggi=40) + confidence_gap
        # Sort descending by priority_score
        scores = [b["priority_score"] for b in bundles]
        assert scores == sorted(scores, reverse=True)


# ── Schema tests ───────────────────────────────────────────────────────────

class TestBundleSchema:
    """Verify bundle output contract matches what frontend expects."""

    def test_all_required_fields_present(self):
        recs = [
            _rec("r1", "A", "kritis", "high", 90.0),
            _rec("r2", "B", "kritis", "high", 85.0),
        ]
        bundles = generate_bundles(recs)
        for b in bundles:
            assert "bundle_id" in b
            assert "name" in b
            assert "reason" in b
            assert "bundle_type" in b
            assert "commodities" in b
            assert "missing_information" in b
            assert "priority_score" in b

    def test_commodity_fields_present(self):
        recs = [
            _rec("r1", "Bawang Merah", "kritis", "high", 90.0),
            _rec("r2", "Cabai", "kritis", "high", 85.0),
        ]
        bundles = generate_bundles(recs)
        for b in bundles:
            for c in b["commodities"]:
                assert "recommendation_id" in c
                assert "name" in c
                assert "risk_level" in c
                assert "display_priority_score" in c

    def test_bundle_ids_are_unique(self):
        recs = [
            _rec("r1", "A", "kritis", "high", 90.0),
            _rec("r2", "B", "kritis", "high", 85.0),
            _rec("r3", "Cabai Merah Besar", "sedang", "high", 50.0),
            _rec("r4", "Cabai Rawit Merah", "sedang", "high", 48.0),
        ]
        bundles = generate_bundles(recs)
        ids = [b["bundle_id"] for b in bundles]
        assert len(ids) == len(set(ids))

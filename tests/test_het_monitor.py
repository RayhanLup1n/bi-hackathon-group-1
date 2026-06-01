"""
Tests for HET Monitor Engine (src/engine/het_monitor.py).

Tests all HET status levels:
  AMAN       — harga < 80% HET
  WASPADA    — 80% <= harga < 100% HET
  KRITIS     — harga == 100% HET
  MELAMPAUI  — harga > 100% HET
  TIDAK_TERSEDIA — no HET reference

Also tests check_het_all() and get_het_summary().
"""
import pytest

from src.engine.het_monitor import (
    HETStatus,
    HETResult,
    check_het_status,
    check_het_all,
    get_het_summary,
)


class TestCheckHetStatus:
    """Tests for single commodity HET check."""

    def test_aman_well_below_het(self):
        """Price 50% of HET → AMAN."""
        result = check_het_status("com_11", 20_000, "Bawang Merah")
        # HET for com_11 = 40,000 → 20,000/40,000 = 50%
        assert result.status == HETStatus.AMAN
        assert result.pct_of_het == 50.0
        assert result.selisih == -20_000

    def test_aman_just_below_waspada(self):
        """Price 79% of HET → still AMAN."""
        result = check_het_status("com_11", 31_600, "Bawang Merah")
        # 31,600/40,000 = 79%
        assert result.status == HETStatus.AMAN

    def test_waspada_at_80_percent(self):
        """Price exactly 80% of HET → WASPADA."""
        result = check_het_status("com_11", 32_000, "Bawang Merah")
        # 32,000/40,000 = 80%
        assert result.status == HETStatus.WASPADA
        assert result.pct_of_het == 80.0

    def test_waspada_between_80_and_95(self):
        """Price 90% of HET -> WASPADA."""
        result = check_het_status("com_11", 36_000, "Bawang Merah")
        # 36,000/40,000 = 90%
        assert result.status == HETStatus.WASPADA
        assert result.pct_of_het == 90.0

    def test_kritis_at_95_percent(self):
        """Price 95% of HET -> KRITIS (approaching limit)."""
        result = check_het_status("com_11", 38_000, "Bawang Merah")
        # 38,000/40,000 = 95%
        assert result.status == HETStatus.KRITIS
        assert result.pct_of_het == 95.0

    def test_kritis_at_100_percent(self):
        """Price exactly 100% of HET → KRITIS."""
        result = check_het_status("com_11", 40_000, "Bawang Merah")
        # 40,000/40,000 = 100%
        assert result.status == HETStatus.KRITIS
        assert result.pct_of_het == 100.0
        assert result.selisih == 0

    def test_melampaui_above_het(self):
        """Price 120% of HET → MELAMPAUI."""
        result = check_het_status("com_11", 48_000, "Bawang Merah")
        # 48,000/40,000 = 120%
        assert result.status == HETStatus.MELAMPAUI
        assert result.pct_of_het == 120.0
        assert result.selisih == 8_000

    def test_tidak_tersedia_unknown_comcat(self):
        """Unknown comcat_id → TIDAK_TERSEDIA."""
        result = check_het_status("com_99", 30_000, "Unknown")
        assert result.status == HETStatus.TIDAK_TERSEDIA
        assert result.het_harga is None

    def test_tidak_tersedia_zero_price(self):
        """Zero price → TIDAK_TERSEDIA."""
        result = check_het_status("com_11", 0, "Bawang Merah")
        assert result.status == HETStatus.TIDAK_TERSEDIA

    def test_result_has_all_fields(self):
        """Verify all fields are populated correctly."""
        result = check_het_status("com_16", 85_000, "Cabai Rawit Merah")
        # HET for com_16 = 70,000 → 85,000/70,000 = 121.4%
        assert result.comcat_id == "com_16"
        assert result.komoditas_nama == "Cabai Rawit Merah"
        assert result.harga_aktual == 85_000
        assert result.het_harga == 70_000
        assert result.pct_of_het is not None
        assert result.selisih == 15_000
        assert len(result.keterangan) > 0

    def test_cabai_rawit_merah_highest_het(self):
        """Cabai Rawit Merah has highest HET (70,000)."""
        # Price just below HET
        result = check_het_status("com_16", 65_000, "Cabai Rawit Merah")
        assert result.status == HETStatus.WASPADA  # 65/70 = 92.9%
        assert result.het_harga == 70_000


class TestCheckHetAll:
    """Tests for bulk HET check."""

    def test_multiple_commodities(self):
        """Check all 6 MVP commodities at once."""
        prices = {
            "com_11": (20_000, "Bawang Merah"),      # AMAN (50%)
            "com_12": (38_000, "Bawang Putih"),      # WASPADA (84%)
            "com_13": (55_000, "Cabai Merah Besar"), # KRITIS (100%)
            "com_14": (60_000, "Cabai Merah Keriting"),  # MELAMPAUI (120%)
            "com_15": (30_000, "Cabai Rawit Hijau"),  # AMAN (50%)
            "com_16": (75_000, "Cabai Rawit Merah"),  # MELAMPAUI (107%)
        }
        results = check_het_all(prices)

        assert len(results) == 6
        # Should be sorted by severity (melampaui first)
        assert results[0].status == HETStatus.MELAMPAUI
        assert results[-1].status == HETStatus.AMAN

    def test_sorted_by_severity(self):
        """Results should be sorted: melampaui > kritis > waspada > aman."""
        prices = {
            "com_11": (20_000, "Bawang Merah"),      # AMAN
            "com_12": (50_000, "Bawang Putih"),      # MELAMPAUI
            "com_13": (55_000, "Cabai Merah Besar"), # KRITIS
        }
        results = check_het_all(prices)

        statuses = [r.status for r in results]
        assert statuses[0] == HETStatus.MELAMPAUI
        assert statuses[-1] == HETStatus.AMAN


class TestGetHetSummary:
    """Tests for HET summary generation."""

    def test_summary_counts(self):
        """Summary should count each status correctly."""
        results = [
            HETResult(comcat_id="com_11", komoditas_nama="A", status=HETStatus.AMAN, harga_aktual=20000),
            HETResult(comcat_id="com_12", komoditas_nama="B", status=HETStatus.WASPADA, harga_aktual=38000),
            HETResult(comcat_id="com_13", komoditas_nama="C", status=HETStatus.MELAMPAUI, harga_aktual=60000),
        ]
        summary = get_het_summary(results)

        assert summary["total"] == 3
        assert summary["per_status"]["aman"] == 1
        assert summary["per_status"]["waspada"] == 1
        assert summary["per_status"]["melampaui"] == 1
        assert summary["ada_melampaui"] is True

    def test_summary_no_critical(self):
        """Summary with no critical items."""
        results = [
            HETResult(comcat_id="com_11", komoditas_nama="A", status=HETStatus.AMAN, harga_aktual=20000),
            HETResult(comcat_id="com_12", komoditas_nama="B", status=HETStatus.AMAN, harga_aktual=30000),
        ]
        summary = get_het_summary(results)

        assert summary["ada_melampaui"] is False
        assert summary["ada_kritis"] is False


class TestHETThresholdBoundaries:
    """Verify exact boundaries align with config/settings.py thresholds.

    Settings: WASPADA=80%, KRITIS=95%, MELAMPAUI=100%
    """

    def test_boundary_79_is_aman(self):
        """79.9% → AMAN (just below WASPADA threshold)."""
        # com_12 HET = 45,000 → 79.9% = 35,955
        result = check_het_status("com_12", 35_955, "Bawang Putih")
        assert result.status == HETStatus.AMAN

    def test_boundary_80_is_waspada(self):
        """80.0% → WASPADA."""
        # com_12 HET = 45,000 → 80% = 36,000
        result = check_het_status("com_12", 36_000, "Bawang Putih")
        assert result.status == HETStatus.WASPADA

    def test_boundary_94_is_waspada(self):
        """94.9% → still WASPADA (below 95% KRITIS boundary)."""
        # com_12 HET = 45,000 → 94.4% = 42,500
        result = check_het_status("com_12", 42_500, "Bawang Putih")
        assert result.status == HETStatus.WASPADA

    def test_boundary_95_is_kritis(self):
        """95.0% → KRITIS."""
        # com_12 HET = 45,000 → 95% = 42,750
        result = check_het_status("com_12", 42_750, "Bawang Putih")
        assert result.status == HETStatus.KRITIS

    def test_boundary_100_is_kritis(self):
        """100.0% → KRITIS (exactly at HET, not yet exceeding)."""
        # com_12 HET = 45,000 → 100% = 45,000
        result = check_het_status("com_12", 45_000, "Bawang Putih")
        assert result.status == HETStatus.KRITIS

    def test_boundary_101_is_melampaui(self):
        """100.1% → MELAMPAUI (exceeds HET)."""
        # com_12 HET = 45,000 → ~100.2% = 45,100
        result = check_het_status("com_12", 45_100, "Bawang Putih")
        assert result.status == HETStatus.MELAMPAUI

    def test_negative_price_is_tidak_tersedia(self):
        """Negative price is treated as invalid."""
        result = check_het_status("com_11", -1000, "Bawang Merah")
        assert result.status == HETStatus.TIDAK_TERSEDIA

    def test_keterangan_not_empty_for_valid_status(self):
        """All valid statuses should have a non-empty keterangan."""
        for price, expected in [(20_000, HETStatus.AMAN), (36_000, HETStatus.WASPADA),
                                (42_750, HETStatus.KRITIS), (50_000, HETStatus.MELAMPAUI)]:
            result = check_het_status("com_12", price, "Bawang Putih")
            assert result.status == expected
            assert len(result.keterangan) > 0, f"Empty keterangan for {expected}"

    def test_all_6_mvp_commodities_have_het(self):
        """All 6 MVP commodities should have HET reference data."""
        for comcat_id in ["com_11", "com_12", "com_13", "com_14", "com_15", "com_16"]:
            result = check_het_status(comcat_id, 30_000, "Test")
            assert result.status != HETStatus.TIDAK_TERSEDIA, (
                f"{comcat_id} has no HET reference"
            )

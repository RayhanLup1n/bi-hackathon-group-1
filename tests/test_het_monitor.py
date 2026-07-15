"""
Tests for HET Monitor Engine (src/engine/het_monitor.py).

Tests all HET status levels:
  AMAN       — harga < 80% HET
  WASPADA    — 80% <= harga < 95% HET
  KRITIS     — 95% <= harga <= 100% HET
  MELAMPAUI  — harga > 100% HET
  TIDAK_TERSEDIA — no HET reference

HET references updated per Peraturan Bapanas No. 12/2024:
  com_11 (Bawang Merah):        41,500
  com_12 (Bawang Putih):        38,000
  com_13 (Cabai Merah Besar):   55,000
  com_14 (Cabai Merah Keriting): 55,000
  com_15 (Cabai Rawit Hijau):   60,000
  com_16 (Cabai Rawit Merah):   57,000

Also tests check_het_all() and get_het_summary().
"""
import pytest

from src.domain.engines.het_monitor import (
    HETStatus,
    HETResult,
    check_het_status,
    check_het_all,
    get_het_summary,
)


class TestCheckHetStatus:
    """Tests for single commodity HET check."""

    def test_aman_well_below_het(self):
        """Price 48.2% of HET -> AMAN."""
        result = check_het_status("com_11", 20_000, "Bawang Merah")
        # HET for com_11 = 41,500 -> 20,000/41,500 = 48.2%
        assert result.status == HETStatus.AMAN
        assert result.pct_of_het == 48.2
        assert result.selisih == -21_500

    def test_aman_just_below_waspada(self):
        """Price 79.5% of HET -> still AMAN."""
        # 79.5% of 41,500 = 33,000
        result = check_het_status("com_11", 33_000, "Bawang Merah")
        assert result.status == HETStatus.AMAN

    def test_waspada_at_80_percent(self):
        """Price exactly 80% of HET -> WASPADA."""
        # 80% of 41,500 = 33,200
        result = check_het_status("com_11", 33_200, "Bawang Merah")
        assert result.status == HETStatus.WASPADA
        assert result.pct_of_het == 80.0

    def test_waspada_between_80_and_95(self):
        """Price 90% of HET -> WASPADA."""
        # 90% of 41,500 = 37,350
        result = check_het_status("com_11", 37_350, "Bawang Merah")
        assert result.status == HETStatus.WASPADA
        assert result.pct_of_het == 90.0

    def test_kritis_at_95_percent(self):
        """Price 95% of HET -> KRITIS (approaching limit)."""
        # 95% of 41,500 = 39,425
        result = check_het_status("com_11", 39_425, "Bawang Merah")
        assert result.status == HETStatus.KRITIS
        assert result.pct_of_het == 95.0

    def test_kritis_at_100_percent(self):
        """Price exactly 100% of HET -> KRITIS."""
        result = check_het_status("com_11", 41_500, "Bawang Merah")
        # 41,500/41,500 = 100%
        assert result.status == HETStatus.KRITIS
        assert result.pct_of_het == 100.0
        assert result.selisih == 0

    def test_melampaui_above_het(self):
        """Price 120% of HET -> MELAMPAUI."""
        # 120% of 41,500 = 49,800
        result = check_het_status("com_11", 49_800, "Bawang Merah")
        assert result.status == HETStatus.MELAMPAUI
        assert result.pct_of_het == 120.0
        assert result.selisih == 8_300

    def test_tidak_tersedia_unknown_comcat(self):
        """Unknown comcat_id -> TIDAK_TERSEDIA."""
        result = check_het_status("com_99", 30_000, "Unknown")
        assert result.status == HETStatus.TIDAK_TERSEDIA
        assert result.het_harga is None

    def test_tidak_tersedia_zero_price(self):
        """Zero price -> TIDAK_TERSEDIA."""
        result = check_het_status("com_11", 0, "Bawang Merah")
        assert result.status == HETStatus.TIDAK_TERSEDIA

    def test_result_has_all_fields(self):
        """Verify all fields are populated correctly."""
        result = check_het_status("com_16", 80_000, "Cabai Rawit Merah")
        # HET for com_16 = 57,000 -> 80,000/57,000 = 140.4%
        assert result.comcat_id == "com_16"
        assert result.komoditas_nama == "Cabai Rawit Merah"
        assert result.harga_aktual == 80_000
        assert result.het_harga == 57_000
        assert result.pct_of_het is not None
        assert result.selisih == 23_000
        assert len(result.keterangan) > 0

    def test_cabai_rawit_hijau_highest_het(self):
        """Cabai Rawit Hijau now has highest HET (60,000) per 12/2024."""
        # Price just below HET: 55,000/60,000 = 91.7%
        result = check_het_status("com_15", 55_000, "Cabai Rawit Hijau")
        assert result.status == HETStatus.WASPADA
        assert result.het_harga == 60_000


class TestCheckHetAll:
    """Tests for bulk HET check."""

    def test_multiple_commodities(self):
        """Check all 6 MVP commodities at once with new HET values."""
        prices = {
            "com_11": (20_000, "Bawang Merah"),          # AMAN (48.2%)
            "com_12": (38_000, "Bawang Putih"),          # KRITIS (100.0%)
            "com_13": (55_000, "Cabai Merah Besar"),     # KRITIS (100.0%)
            "com_14": (60_000, "Cabai Merah Keriting"),  # MELAMPAUI (109.1%)
            "com_15": (30_000, "Cabai Rawit Hijau"),     # AMAN (50.0%)
            "com_16": (75_000, "Cabai Rawit Merah"),     # MELAMPAUI (131.6%)
        }
        results = check_het_all(prices)

        assert len(results) == 6
        # Should be sorted by severity (melampaui first)
        assert results[0].status == HETStatus.MELAMPAUI
        assert results[-1].status == HETStatus.AMAN

    def test_sorted_by_severity(self):
        """Results should be sorted: melampaui > kritis > waspada > aman."""
        prices = {
            "com_11": (20_000, "Bawang Merah"),          # AMAN
            "com_12": (50_000, "Bawang Putih"),          # MELAMPAUI (131.6%)
            "com_13": (55_000, "Cabai Merah Besar"),     # KRITIS (100%)
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
    Uses com_12 (Bawang Putih) HET = 38,000 for boundary tests.
    """

    def test_boundary_79_is_aman(self):
        """79.9% -> AMAN (just below WASPADA threshold)."""
        # 79.9% of 38,000 = 30,362
        result = check_het_status("com_12", 30_362, "Bawang Putih")
        assert result.status == HETStatus.AMAN

    def test_boundary_80_is_waspada(self):
        """80.0% -> WASPADA."""
        # 80% of 38,000 = 30,400
        result = check_het_status("com_12", 30_400, "Bawang Putih")
        assert result.status == HETStatus.WASPADA

    def test_boundary_94_is_waspada(self):
        """94.4% -> still WASPADA (below 95% KRITIS boundary)."""
        # 94.4% of 38,000 = 35,872
        result = check_het_status("com_12", 35_872, "Bawang Putih")
        assert result.status == HETStatus.WASPADA

    def test_boundary_95_is_kritis(self):
        """95.0% -> KRITIS."""
        # 95% of 38,000 = 36,100
        result = check_het_status("com_12", 36_100, "Bawang Putih")
        assert result.status == HETStatus.KRITIS

    def test_boundary_100_is_kritis(self):
        """100.0% -> KRITIS (exactly at HET, not yet exceeding)."""
        result = check_het_status("com_12", 38_000, "Bawang Putih")
        assert result.status == HETStatus.KRITIS

    def test_boundary_101_is_melampaui(self):
        """100.3% -> MELAMPAUI (exceeds HET)."""
        # ~100.3% of 38,000 = 38,100
        result = check_het_status("com_12", 38_100, "Bawang Putih")
        assert result.status == HETStatus.MELAMPAUI

    def test_negative_price_is_tidak_tersedia(self):
        """Negative price is treated as invalid."""
        result = check_het_status("com_11", -1000, "Bawang Merah")
        assert result.status == HETStatus.TIDAK_TERSEDIA

    def test_keterangan_not_empty_for_valid_status(self):
        """All valid statuses should have a non-empty keterangan."""
        # Using com_12 (Bawang Putih) HET = 38,000
        for price, expected in [
            (20_000, HETStatus.AMAN),
            (30_400, HETStatus.WASPADA),
            (36_100, HETStatus.KRITIS),
            (50_000, HETStatus.MELAMPAUI),
        ]:
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

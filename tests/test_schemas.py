"""
Tests for Pydantic schemas (src/models/schemas.py).

Validates:
  - Required fields raise ValidationError when missing
  - Default values work correctly
  - Enum values are enforced
  - Type coercion (e.g., int price)
  - Edge cases: empty lists, boundary values
"""
import pytest
from pydantic import ValidationError

from src.domain.schemas.models import (
    CommodityData, CuacaInfo, KotaInfo, StokInfo,
    CheckResult, RCAResult, DiagnosisType,
)
from src.domain.engines.bowtie_engine import Barrier, BowtieResult
from src.domain.engines.het_monitor import HETResult, HETStatus


# ── DiagnosisType Enum ──────────────────────────────────────────────────────


class TestDiagnosisType:
    def test_valid_values(self):
        assert DiagnosisType("demand") == DiagnosisType.DEMAND
        assert DiagnosisType("supply") == DiagnosisType.SUPPLY
        assert DiagnosisType("distribusi") == DiagnosisType.DISTRIBUSI
        assert DiagnosisType("ekspektasi") == DiagnosisType.EKSPEKTASI
        assert DiagnosisType("unknown") == DiagnosisType.UNKNOWN

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            DiagnosisType("invalid")

    def test_is_string_enum(self):
        """DiagnosisType should serialize as string."""
        assert DiagnosisType.DEMAND == "demand"
        assert str(DiagnosisType.SUPPLY) == "DiagnosisType.SUPPLY"


# ── CuacaInfo ───────────────────────────────────────────────────────────────


class TestCuacaInfo:
    def test_minimal_valid(self):
        c = CuacaInfo(ekstrem=False, desc="Cerah")
        assert c.ekstrem is False
        assert c.desc == "Cerah"
        assert c.daerah == ""
        assert c.detail == ""

    def test_all_fields(self):
        c = CuacaInfo(
            ekstrem=True, desc="Hujan Lebat",
            daerah="Jawa Barat", detail="120mm curah hujan",
        )
        assert c.ekstrem is True
        assert c.daerah == "Jawa Barat"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            CuacaInfo(ekstrem=True)  # missing desc


# ── StokInfo ────────────────────────────────────────────────────────────────


class TestStokInfo:
    def test_default_pct(self):
        s = StokInfo(status="Normal", kelas="ok")
        assert s.pct == 0.0

    def test_with_pct(self):
        s = StokInfo(status="Menipis", kelas="warn", pct=0.45)
        assert s.pct == 0.45

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            StokInfo(status="Normal")  # missing kelas


# ── KotaInfo ────────────────────────────────────────────────────────────────


class TestKotaInfo:
    def test_valid(self):
        k = KotaInfo(nama="Bandung", naik=True)
        assert k.nama == "Bandung"
        assert k.naik is True

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            KotaInfo(nama="Bandung")  # missing naik


# ── CommodityData ───────────────────────────────────────────────────────────


class TestCommodityData:
    def test_minimal_valid(self):
        cd = CommodityData(
            key="test", name="Test", price_now=20000, price_prev=18000,
            price_threshold=10.0,
            cuaca=CuacaInfo(ekstrem=False, desc="Cerah"),
            kota_list=[],
            stok=StokInfo(status="Normal", kelas="ok"),
        )
        assert cd.key == "test"
        assert cd.ml_pred is None
        assert cd.threshold_kota == 0.6

    def test_with_ml_pred(self):
        cd = CommodityData(
            key="test", name="Test", price_now=20000, price_prev=18000,
            price_threshold=10.0, ml_pred=22000,
            cuaca=CuacaInfo(ekstrem=False, desc="Cerah"),
            kota_list=[], stok=StokInfo(status="Normal", kelas="ok"),
        )
        assert cd.ml_pred == 22000

    def test_empty_kota_list_allowed(self):
        cd = CommodityData(
            key="test", name="Test", price_now=20000, price_prev=18000,
            price_threshold=10.0,
            cuaca=CuacaInfo(ekstrem=False, desc="Cerah"),
            kota_list=[],
            stok=StokInfo(status="Normal", kelas="ok"),
        )
        assert cd.kota_list == []

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            CommodityData(key="test")  # missing many fields


# ── CheckResult ─────────────────────────────────────────────────────────────


class TestCheckResult:
    def test_valid_statuses(self):
        for status in ["triggered", "clear", "skip"]:
            cr = CheckResult(step=1, nama="Test", status=status, detail="—")
            assert cr.status == status

    def test_all_fields_populated(self):
        cr = CheckResult(step=2, nama="Cek Cuaca", status="triggered", detail="Hujan lebat")
        assert cr.step == 2
        assert cr.nama == "Cek Cuaca"


# ── RCAResult ───────────────────────────────────────────────────────────────


class TestRCAResult:
    def test_defaults(self):
        r = RCAResult(
            commodity_key="test", commodity_name="Test",
            diagnosis=DiagnosisType.DEMAND, title="T", description="D", action="A",
            checks=[], price_delta_pct=10.0, is_anomaly=True,
        )
        assert r.severity_level == "L0"
        assert r.yes_indicators == []

    def test_with_severity_and_indicators(self):
        r = RCAResult(
            commodity_key="test", commodity_name="Test",
            diagnosis=DiagnosisType.SUPPLY, title="T", description="D", action="A",
            checks=[], price_delta_pct=15.0, is_anomaly=True,
            severity_level="L3",
            yes_indicators=["G1: Anomali Harga", "S1: Cuaca Ekstrem"],
        )
        assert r.severity_level == "L3"
        assert len(r.yes_indicators) == 2

    def test_serializable(self):
        r = RCAResult(
            commodity_key="test", commodity_name="Test",
            diagnosis=DiagnosisType.DEMAND, title="T", description="D", action="A",
            checks=[CheckResult(step=1, nama="X", status="clear", detail="—")],
            price_delta_pct=10.0, is_anomaly=True,
        )
        data = r.model_dump()
        assert data["diagnosis"] == "demand"
        assert len(data["checks"]) == 1


# ── HETResult ───────────────────────────────────────────────────────────────


class TestHETResultSchema:
    def test_minimal(self):
        r = HETResult(
            comcat_id="com_11", komoditas_nama="Bawang Merah",
            status=HETStatus.AMAN, harga_aktual=20000,
        )
        assert r.het_harga is None
        assert r.pct_of_het is None
        assert r.selisih is None
        assert r.keterangan == ""

    def test_full(self):
        r = HETResult(
            comcat_id="com_11", komoditas_nama="Bawang Merah",
            status=HETStatus.WASPADA, harga_aktual=36000,
            het_harga=40000, pct_of_het=90.0, selisih=-4000,
            keterangan="Mendekati batas",
        )
        assert r.selisih == -4000

    def test_status_enum_values(self):
        for val in ["aman", "waspada", "kritis", "melampaui", "tidak_tersedia"]:
            assert HETStatus(val).value == val


# ── BowtieResult ────────────────────────────────────────────────────────────


class TestBowtieResultSchema:
    def test_barrier_model(self):
        b = Barrier(
            id="P1", name="Test", description="Desc",
            threat_ids=["D1"], active=True,
        )
        assert b.active is True
        assert b.threat_ids == ["D1"]

    def test_barrier_default_inactive(self):
        b = Barrier(id="P1", name="Test", description="Desc", threat_ids=["D1"])
        assert b.active is False

    def test_bowtie_result_serializable(self):
        result = BowtieResult(
            commodity_key="test", commodity_name="Test",
            hazard_event="Test Hazard", severity_level="L1",
            active_threats=[{"id": "D1", "name": "Test", "type": "demand", "active": True}],
            prevention=[Barrier(id="P1", name="T", description="D", threat_ids=["D1"])],
            mitigation=[Barrier(id="M1", name="T", description="D", threat_ids=["D1"])],
            summary="1 ancaman aktif",
        )
        data = result.model_dump()
        assert isinstance(data["prevention"], list)
        assert isinstance(data["mitigation"], list)

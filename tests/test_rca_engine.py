"""
Tests untuk RCA Rule Engine.
Jalankan dengan: pytest tests/
"""
import pytest
from datetime import date
from unittest.mock import patch
from src.models.schemas import CommodityData, CuacaInfo, KotaInfo, StokInfo, DiagnosisType
from src.engine.rca_engine import run_rca


# Patch hari besar cache so tests don't need BigQuery
_TEST_HARI_BESAR = [
    ("Idul Fitri", date(2025, 3, 30)),
    ("Idul Adha", date(2025, 6, 6)),
    ("Hari Kemerdekaan RI", date(2025, 8, 17)),
    ("Idul Fitri", date(2026, 3, 20)),
    ("Idul Adha", date(2026, 5, 27)),
]


@pytest.fixture(autouse=True)
def _mock_hari_besar_cache():
    """Inject test calendar into RCA engine so BigQuery is not needed."""
    with patch(
        "src.engine.rca_engine._hari_besar_cache", _TEST_HARI_BESAR
    ):
        yield


def make_commodity(**overrides) -> CommodityData:
    """Factory helper — buat CommodityData dengan default kosong, override sesuai kebutuhan.

    Untuk kemudahan, menerima kota_naik (int) dan total_kota (int) sebagai
    shorthand: N kota pertama di-set naik=True, sisanya False.
    Atau pass kota_list=[KotaInfo(...), ...] secara langsung.
    """
    kota_naik = overrides.pop("kota_naik", 1)
    total_kota = overrides.pop("total_kota", 8)
    default_kota_list = [
        KotaInfo(nama=f"Kota{i + 1}", naik=(i < kota_naik))
        for i in range(total_kota)
    ]

    defaults = dict(
        key="test",
        name="Test Komoditas",
        price_now=20000,
        price_prev=18000,
        price_threshold=10.0,
        ml_pred=None,
        cuaca=CuacaInfo(ekstrem=False, desc="Cerah", daerah=""),
        kota_list=default_kota_list,
        stok=StokInfo(status="Normal", kelas="ok", pct=1.0),
    )
    defaults.update(overrides)
    return CommodityData(**defaults)


# Tanggal yang pasti TIDAK masuk window hari raya manapun di kalender
DATE_NORMAL = date(2025, 9, 15)
# Tanggal yang masuk window Idul Adha 2025 (2025-06-06, H-14 = 2025-05-23)
DATE_IDUL_ADHA = date(2025, 5, 28)


# ── DEMAND SPIKE ────────────────────────────────────────────────────────────

def test_demand_spike_hari_raya():
    """Tanggal masuk window Idul Adha → Demand Spike, semua check lain di-skip."""
    data = make_commodity()
    result = run_rca(data, today=DATE_IDUL_ADHA)

    assert result.diagnosis == DiagnosisType.DEMAND
    assert result.checks[0].status == "triggered"
    assert all(c.status == "skip" for c in result.checks[1:])


def test_demand_spike_hari_kemerdekaan():
    """17 Agustus 2025 terdeteksi dari tanggal 11 Aug (6 hari sebelumnya, < H-14)."""
    data = make_commodity()
    result = run_rca(data, today=date(2025, 8, 11))

    assert result.diagnosis == DiagnosisType.DEMAND
    assert result.checks[0].status == "triggered"
    assert "Kemerdekaan" in result.checks[0].detail


def test_no_demand_spike_outside_window():
    """Tanggal jauh dari hari besar manapun → tidak trigger demand spike."""
    data = make_commodity()
    result = run_rca(data, today=DATE_NORMAL)

    assert result.checks[0].status == "clear"


# ── SUPPLY ──────────────────────────────────────────────────────────────────

def test_supply_cuaca_ekstrem():
    """Cuaca ekstrem → Gangguan Supply."""
    data = make_commodity(cuaca=CuacaInfo(ekstrem=True, desc="Banjir", daerah="Jawa Tengah"))
    result = run_rca(data, today=DATE_NORMAL)

    assert result.diagnosis == DiagnosisType.SUPPLY
    assert result.checks[0].status == "clear"
    assert result.checks[1].status == "triggered"
    assert all(c.status == "skip" for c in result.checks[2:])


def test_supply_persebaran_kota():
    """Kenaikan di 6/8 kota (75%) tanpa cuaca → Supply Nasional."""
    data = make_commodity(kota_naik=6, total_kota=8)
    result = run_rca(data, today=DATE_NORMAL)

    assert result.diagnosis == DiagnosisType.SUPPLY
    assert result.checks[2].status == "triggered"


def test_supply_threshold_kota_batas():
    """Tepat di threshold 60% → trigger."""
    data = make_commodity(kota_naik=3, total_kota=5, threshold_kota=0.6)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.diagnosis == DiagnosisType.SUPPLY


def test_supply_threshold_kota_bawah():
    """Di bawah threshold 60% (2/8 = 25%) → persebaran kota tidak trigger."""
    data = make_commodity(kota_naik=2, total_kota=8)
    result = run_rca(data, today=DATE_NORMAL)
    # Check 3 (persebaran kota) should be clear, not triggered
    assert result.checks[2].status == "clear"


# ── DISTRIBUSI ──────────────────────────────────────────────────────────────

def test_distribusi_lokal():
    """Tidak ada trigger lain, stok normal → Distribusi Lokal."""
    data = make_commodity(kota_naik=1, total_kota=8)
    result = run_rca(data, today=DATE_NORMAL)

    assert result.diagnosis == DiagnosisType.DISTRIBUSI
    assert all(c.status == "clear" for c in result.checks)


# ── UNKNOWN ─────────────────────────────────────────────────────────────────

def test_unknown_stok_menipis():
    """Tidak ada trigger lain, stok menipis → Unknown."""
    data = make_commodity(
        kota_naik=1,
        total_kota=8,
        stok=StokInfo(status="Menipis", kelas="warn"),
    )
    result = run_rca(data, today=DATE_NORMAL)
    assert result.diagnosis == DiagnosisType.UNKNOWN


# ── DELTA & ANOMALY ─────────────────────────────────────────────────────────

def test_delta_pct_calculation():
    """Cek kalkulasi delta persen harga."""
    data = make_commodity(price_now=22000, price_prev=20000)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.price_delta_pct == pytest.approx(10.0)


def test_anomaly_flag_above_threshold():
    data = make_commodity(price_now=22000, price_prev=20000, price_threshold=10.0)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.is_anomaly is True


def test_anomaly_flag_below_threshold():
    data = make_commodity(price_now=21000, price_prev=20000, price_threshold=10.0)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.is_anomaly is False


# ── OUTPUT STRUCTURE ────────────────────────────────────────────────────────

def test_result_always_has_4_checks():
    """RCA selalu return tepat 4 check items."""
    for kota in [0, 1, 4, 8]:
        data = make_commodity(kota_naik=kota)
        result = run_rca(data, today=DATE_NORMAL)
        assert len(result.checks) == 4


def test_result_fields_not_empty():
    data = make_commodity()
    result = run_rca(data, today=DATE_NORMAL)
    assert result.title
    assert result.description
    assert result.action


# -- EDGE CASES ----------------------------------------------------------

def test_price_prev_zero_no_division_error():
    """price_prev=0 should not raise ZeroDivisionError, delta_pct should be 0."""
    data = make_commodity(price_now=20000, price_prev=0)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.price_delta_pct == 0.0
    assert result.is_anomaly is False


def test_empty_kota_list_no_error():
    """Empty kota_list should not crash, persebaran check should be skipped."""
    data = make_commodity(kota_naik=0, total_kota=0)
    result = run_rca(data, today=DATE_NORMAL)
    assert len(result.checks) == 4
    # Persebaran kota check (index 2) should not crash
    assert result.checks[2].status in ("clear", "skip")


def test_het_boundary_exact_threshold():
    """Exactly at kota threshold boundary (60%) should trigger."""
    # 3/5 = 60% - exactly at threshold
    data = make_commodity(kota_naik=3, total_kota=5, threshold_kota=0.6)
    result = run_rca(data, today=DATE_NORMAL)
    assert result.checks[2].status == "triggered"

    # 2/5 = 40% - below threshold
    data2 = make_commodity(kota_naik=2, total_kota=5, threshold_kota=0.6)
    result2 = run_rca(data2, today=DATE_NORMAL)
    assert result2.checks[2].status == "clear"


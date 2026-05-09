"""
RCA Rule Engine — Decision Tree untuk Root Cause Analysis inflasi harga pangan.

Urutan pemeriksaan:
  1. Cek Hari Raya        → Demand Spike
  2. Cek Cuaca (Open-Meteo) → Gangguan Supply
  3. Cek Persebaran Kota  → Supply Nasional
  4. Cek Stok Pedagang    → Distribusi Lokal / Unknown

Untuk menambah rule baru, tambahkan method _check_*() dan daftarkan
di RULE_SEQUENCE di bawah.
"""

from datetime import date

from config.settings import HARI_RAYA_CALENDAR, HARI_RAYA_WINDOW_DAYS, HARI_RAYA_POST_WINDOW_DAYS
from src.models.schemas import (
    CommodityData, RCAResult, CheckResult, DiagnosisType
)

# ──────────────────────────────────────────────
# DIAGNOSIS TEMPLATES
# Edit teks di sini untuk ubah narasi output
# ──────────────────────────────────────────────

DIAGNOSIS_TEMPLATES: dict[DiagnosisType, dict] = {
    DiagnosisType.DEMAND: {
        "title": "Demand Spike",
        "description": (
            "Kenaikan harga kemungkinan besar dipicu oleh lonjakan permintaan "
            "menjelang hari raya. Pola ini musiman dan biasanya koreksi sendiri setelahnya."
        ),
        "action": (
            "Pantau saja. Balancing stock tidak efektif karena masalah bukan di supply — "
            "stok tersedia tapi permintaan memang tinggi. "
            "Optimalkan distribusi ke titik keramaian."
        ),
    },
    DiagnosisType.SUPPLY: {
        "title": "Gangguan Supply",
        "description": (
            "Kenaikan terjadi bersamaan dengan cuaca ekstrem di daerah produksi utama. "
            "Indikasi kuat bahwa panen atau distribusi terganggu."
        ),
        "action": (
            "Koordinasi ke Bulog/Kementan untuk cek stok buffer nasional. "
            "Pertimbangkan impor darurat atau relokasi stok dari daerah surplus "
            "yang tidak terdampak cuaca."
        ),
    },
    DiagnosisType.DISTRIBUSI: {
        "title": "Bottleneck Distribusi Lokal",
        "description": (
            "Kenaikan hanya terjadi di satu kota tanpa pemicu cuaca maupun demand. "
            "Indikasi ada hambatan di rantai distribusi — bukan masalah supply nasional."
        ),
        "action": (
            "Balancing stock relevan di sini. Identifikasi daerah surplus terdekat "
            "dan koordinasikan pengiriman. Cek juga kondisi jalan atau isu logistik lokal."
        ),
    },
    DiagnosisType.UNKNOWN: {
        "title": "Penyebab Belum Teridentifikasi",
        "description": (
            "Tidak ada trigger yang cukup kuat terdeteksi. "
            "Kenaikan mungkin masih dalam batas wajar atau membutuhkan investigasi manual."
        ),
        "action": (
            "Tingkatkan frekuensi monitoring. Lakukan survei lapangan untuk konfirmasi "
            "kondisi supply dan distribusi sebelum mengambil keputusan intervensi."
        ),
    },
}


# ──────────────────────────────────────────────
# INDIVIDUAL CHECK FUNCTIONS
# Tambah fungsi _check_*() baru di sini untuk extend rule tree
# ──────────────────────────────────────────────

def _check_hari_raya(data: CommodityData, today: date) -> CheckResult:
    """Check 1: Apakah hari ini masuk window hari raya? (H-14 s/d H+3)
    Kalender dibaca dari config/settings.py — tidak bergantung pada field per-komoditas.
    """
    for nama, tgl_str in HARI_RAYA_CALENDAR:
        tgl = date.fromisoformat(tgl_str)
        delta = (tgl - today).days   # positif = hari raya belum tiba
        if -HARI_RAYA_POST_WINDOW_DAYS <= delta <= HARI_RAYA_WINDOW_DAYS:
            if delta > 0:
                desc = f"dalam {delta} hari"
            elif delta == 0:
                desc = "hari ini"
            else:
                desc = f"{abs(delta)} hari yang lalu"
            return CheckResult(
                step=1,
                nama="Cek Kalender Hari Raya",
                status="triggered",
                detail=(
                    f"⚠ {nama} {desc} — window demand spike aktif "
                    f"(H-{HARI_RAYA_WINDOW_DAYS} s/d H+{HARI_RAYA_POST_WINDOW_DAYS})"
                ),
            )
    return CheckResult(
        step=1,
        nama="Cek Kalender Hari Raya",
        status="clear",
        detail=(
            f"Tidak ada hari raya dalam {HARI_RAYA_WINDOW_DAYS} hari ke depan "
            f"— bukan demand spike musiman"
        ),
    )


def _check_cuaca(data: CommodityData) -> CheckResult:
    """Check 2: Ada cuaca ekstrem di daerah produksi? (sumber: Open-Meteo Historical API)"""
    cuaca = data.cuaca
    if cuaca.ekstrem:
        return CheckResult(
            step=2,
            nama="Cek Cuaca Ekstrem (Open-Meteo)",
            status="triggered",
            detail=(
                f"⚠ {cuaca.desc} terdeteksi di daerah produksi "
                f"({cuaca.daerah}) — potensi gangguan panen"
            ),
        )
    return CheckResult(
        step=2,
        nama="Cek Cuaca Ekstrem (Open-Meteo)",
        status="clear",
        detail=f"Cuaca: {cuaca.desc} — tidak ada cuaca ekstrem terdeteksi",
    )


def _check_persebaran_kota(data: CommodityData) -> CheckResult:
    """Check 3: Apakah kenaikan merata di banyak kota? (threshold default 60%)"""
    kota_naik = [k for k in data.kota_list if k.naik]
    total_kota = len(data.kota_list)
    pct = len(kota_naik) / total_kota
    nama_naik = ", ".join(k.nama for k in kota_naik) if kota_naik else "—"
    if pct >= data.threshold_kota:
        return CheckResult(
            step=3,
            nama="Cek Persebaran Kenaikan Antar Kota",
            status="triggered",
            detail=(
                f"⚠ {len(kota_naik)} dari {total_kota} kota mengalami kenaikan "
                f"serempak ({pct:.0%}) — indikasi masalah supply nasional\n"
                f"Kota naik: {nama_naik}"
            ),
        )
    return CheckResult(
        step=3,
        nama="Cek Persebaran Kenaikan Antar Kota",
        status="clear",
        detail=(
            f"Hanya {len(kota_naik)} dari {total_kota} kota naik — kenaikan terlokalisir\n"
            f"Kota naik: {nama_naik}"
        ),
    )


def _check_stok(data: CommodityData) -> CheckResult:
    """Check 4: Bagaimana kondisi stok pedagang? (sumber: Badan Pangan / Bulog)"""
    stok = data.stok
    if stok.status == "Normal":
        return CheckResult(
            step=4,
            nama="Cek Stok Pedagang (Badan Pangan)",
            status="clear",
            detail=f"Stok pedagang: {stok.status} — supply tersedia, kemungkinan bottleneck distribusi",
        )
    return CheckResult(
        step=4,
        nama="Cek Stok Pedagang (Badan Pangan)",
        status="triggered",
        detail=f"Stok pedagang: {stok.status} — supply di titik penjualan mulai berkurang",
    )


def _skip(step: int, nama: str, reason: str) -> CheckResult:
    return CheckResult(step=step, nama=nama, status="skip", detail=f"Dilewati — {reason}")


# ──────────────────────────────────────────────
# RULE SEQUENCE
# Urutan pemeriksaan dan kondisi exit masing-masing step
# ──────────────────────────────────────────────

def run_rca(data: CommodityData, today: date | None = None) -> RCAResult:
    """
    Jalankan decision tree RCA secara sequential.
    Return early saat trigger pertama ditemukan.

    today: tanggal referensi untuk cek kalender hari raya.
           Default date.today(). Bisa di-override untuk simulasi.
    """
    if today is None:
        today = date.today()

    checks: list[CheckResult] = []

    # Hitung delta harga
    delta_pct = ((data.price_now - data.price_prev) / data.price_prev) * 100
    is_anomaly = delta_pct >= data.price_threshold

    # ── Check 1: Hari Raya ──────────────────────
    c1 = _check_hari_raya(data, today)
    checks.append(c1)
    if c1.status == "triggered":
        checks += [
            _skip(2, "Cek Cuaca Ekstrem (Open-Meteo)", "demand trigger sudah cukup kuat"),
            _skip(3, "Cek Persebaran Kenaikan Antar Kota", "demand trigger sudah cukup kuat"),
            _skip(4, "Cek Stok Pedagang (Badan Pangan)", "demand trigger sudah cukup kuat"),
        ]
        diagnosis = DiagnosisType.DEMAND
        return _build_result(data, diagnosis, checks, delta_pct, is_anomaly)

    # ── Check 2: Cuaca ──────────────────────────
    c2 = _check_cuaca(data)
    checks.append(c2)
    if c2.status == "triggered":
        checks += [
            _skip(3, "Cek Persebaran Kenaikan Antar Kota", "cuaca trigger ditemukan"),
            _skip(4, "Cek Stok Pedagang (Badan Pangan)", "cuaca trigger ditemukan"),
        ]
        diagnosis = DiagnosisType.SUPPLY
        return _build_result(data, diagnosis, checks, delta_pct, is_anomaly)

    # ── Check 3: Persebaran Kota ────────────────
    c3 = _check_persebaran_kota(data)
    checks.append(c3)
    if c3.status == "triggered":
        checks.append(
            _skip(4, "Cek Stok Pedagang (Badan Pangan)", "persebaran kota trigger ditemukan")
        )
        diagnosis = DiagnosisType.SUPPLY
        return _build_result(data, diagnosis, checks, delta_pct, is_anomaly)

    # ── Check 4: Stok ───────────────────────────
    c4 = _check_stok(data)
    checks.append(c4)
    if c4.status == "clear":
        diagnosis = DiagnosisType.DISTRIBUSI
    else:
        diagnosis = DiagnosisType.UNKNOWN

    return _build_result(data, diagnosis, checks, delta_pct, is_anomaly)


def _build_result(
    data: CommodityData,
    diagnosis: DiagnosisType,
    checks: list[CheckResult],
    delta_pct: float,
    is_anomaly: bool,
) -> RCAResult:
    tmpl = DIAGNOSIS_TEMPLATES[diagnosis]
    return RCAResult(
        commodity_key=data.key,
        commodity_name=data.name,
        diagnosis=diagnosis,
        title=tmpl["title"],
        description=tmpl["description"],
        action=tmpl["action"],
        checks=checks,
        price_delta_pct=round(delta_pct, 2),
        is_anomaly=is_anomaly,
    )

"""
RCA Rule Engine — Decision Tree untuk Root Cause Analysis inflasi harga pangan.

Semua 4 check selalu dijalankan (tidak ada skip).
Diagnosis ditentukan dari check pertama yang triggered:
  1. Cek Hari Raya        → Demand Spike
  2. Cek Cuaca BMKG       → Gangguan Supply
  3. Cek Persebaran Kota  → Supply Nasional
  4. Cek Stok Pedagang    → Distribusi Lokal / Unknown

Severity L0–L4 dihitung terpisah dari seluruh hasil check.
"""

from datetime import date

from config.settings import (
    HARI_RAYA_CALENDAR, HARI_RAYA_WINDOW_DAYS, HARI_RAYA_POST_WINDOW_DAYS,
    STOK_MENIPIS_THRESHOLD,
)
from src.models.schemas import (
    CommodityData, RCAResult, CheckResult, DiagnosisType
)
from src.data.inflasi_db import get_inflasi_tren
from src.data.commodity_data import get_related_deltas

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
    DiagnosisType.EKSPEKTASI: {
        "title": "Tekanan Inflasi Ekspektatif",
        "description": (
            "Tidak ada gangguan supply, cuaca, atau distribusi yang terdeteksi, "
            "namun inflasi bulanan di kota pantauan terus positif selama 3 bulan berturut-turut. "
            "Indikasi kuat bahwa kenaikan harga didorong oleh ekspektasi pelaku pasar, "
            "bukan oleh faktor fundamental yang segera bisa diatasi."
        ),
        "action": (
            "Prioritaskan komunikasi publik dan transparansi harga untuk meredam ekspektasi. "
            "Operasi pasar terbatas di titik-titik strategis. "
            "Pantau apakah pedagang menaikan harga secara preventif — jika ya, "
            "koordinasi dengan Satgas Pangan untuk penertiban."
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
    """Check 2: Ada cuaca ekstrem di daerah produksi? (sumber: BMKG)"""
    cuaca = data.cuaca
    if cuaca.ekstrem:
        return CheckResult(
            step=2,
            nama="Cek Cuaca Ekstrem (BMKG)",
            status="triggered",
            detail=(
                f"⚠ {cuaca.desc} terdeteksi di daerah produksi "
                f"({cuaca.daerah}) — potensi gangguan panen"
            ),
        )
    return CheckResult(
        step=2,
        nama="Cek Cuaca Ekstrem (BMKG)",
        status="clear",
        detail=f"Cuaca: {cuaca.desc} — tidak ada peringatan ekstrem dari BMKG",
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


def _check_cross_commodity(data: CommodityData) -> CheckResult:
    """Check 6: Apakah komoditas terkait juga naik anomali? (korelasi supply chain / substitusi)"""
    related = get_related_deltas(data.key)

    if not related:
        return CheckResult(
            step=6,
            nama="Cek Korelasi Komoditas Terkait",
            status="clear",
            detail="Tidak ada komoditas terkait yang dikonfigurasi",
        )

    anomali = [r for r in related if r["delta_pct"] >= r["threshold"]]
    lines = "\n".join(
        f"{'⚠' if r['delta_pct'] >= r['threshold'] else '·'} "
        f"{r['name']}: +{r['delta_pct']:.1f}% (ambang {r['threshold']:.0f}%)"
        for r in related
    )

    if anomali:
        return CheckResult(
            step=6,
            nama="Cek Korelasi Komoditas Terkait",
            status="triggered",
            detail=(
                f"⚠ {len(anomali)} komoditas terkait juga anomali — "
                f"indikasi gangguan supply chain sistemik\n{lines}"
            ),
        )
    return CheckResult(
        step=6,
        nama="Cek Korelasi Komoditas Terkait",
        status="clear",
        detail=f"Komoditas terkait tidak menunjukkan anomali:\n{lines}",
    )


def _check_inflasi_tren(data: CommodityData, today: date) -> CheckResult:
    """Check 5: Apakah inflasi M-to-M positif 3 bulan berturut di kota pantauan? (sumber: BPS)"""
    kota_names = [k.nama for k in data.kota_list]
    triggered, detail = get_inflasi_tren(kota_names, today)
    return CheckResult(
        step=5,
        nama="Cek Tren Inflasi Bulanan (BPS)",
        status="triggered" if triggered else "clear",
        detail=detail,
    )


# ──────────────────────────────────────────────
# SEVERITY SCORING (5 indikator tersedia dari 10)
# Skala: L0 (aman) → L4 (darurat)
# ──────────────────────────────────────────────

# Label deskriptif per level (untuk display di frontend)
SEVERITY_LABELS: dict[str, str] = {
    "L0": "Aman",
    "L1": "Waspada",
    "L2": "Awas",
    "L3": "Kritis",
    "L4": "Darurat",
}


def _score_severity(
    data: CommodityData, checks: list[CheckResult], delta_pct: float
) -> tuple[str, list[str]]:
    """
    Hitung severity level dari 6 indikator yang datanya tersedia.
    Skoring proporsional terhadap 6 indikator:
      0 → L0, 1 → L1, 2 → L2, 3-4 → L3, 5-6 → L4
    """
    yes: list[str] = []

    # G1 — Anomali harga
    if delta_pct >= data.price_threshold:
        yes.append("G1: Anomali Harga")

    # D1 — Window hari raya aktif
    c1 = next((c for c in checks if c.step == 1), None)
    if c1 and c1.status == "triggered":
        yes.append("D1: Window Hari Raya")

    # S1 — Cuaca ekstrem di daerah produksi
    if data.cuaca.ekstrem:
        yes.append("S1: Cuaca Ekstrem")

    # S3 — Stok menipis atau kritis
    if data.stok.pct < STOK_MENIPIS_THRESHOLD:
        yes.append("S3: Stok Menipis")

    # T2 — Kenaikan serempak antar kota
    kota_naik = sum(1 for k in data.kota_list if k.naik)
    total_kota = len(data.kota_list)
    if total_kota > 0 and kota_naik / total_kota >= data.threshold_kota:
        yes.append("T2: Kenaikan Serempak")

    # E1 — Tren inflasi M-to-M positif 3 bulan berturut (dari BPS)
    c5 = next((c for c in checks if c.step == 5), None)
    if c5 and c5.status == "triggered":
        yes.append("E1: Tren Inflasi 3 Bulan")

    # C1 — Komoditas terkait juga naik anomali (korelasi supply chain)
    c6 = next((c for c in checks if c.step == 6), None)
    if c6 and c6.status == "triggered":
        yes.append("C1: Korelasi Komoditas")

    score = len(yes)
    if score == 0:
        level = "L0"
    elif score == 1:
        level = "L1"
    elif score == 2:
        level = "L2"
    elif score <= 4:
        level = "L3"
    else:
        level = "L4"

    return level, yes


# ──────────────────────────────────────────────
# RULE SEQUENCE
# Urutan pemeriksaan dan kondisi exit masing-masing step
# ──────────────────────────────────────────────

def run_rca(data: CommodityData, today: date | None = None) -> RCAResult:
    """
    Jalankan semua 4 check tanpa early exit.
    Diagnosis ditentukan dari check pertama yang triggered.

    today: tanggal referensi untuk cek kalender hari raya.
           Default date.today(). Bisa di-override untuk simulasi.
    """
    if today is None:
        today = date.today()

    delta_pct = ((data.price_now - data.price_prev) / data.price_prev) * 100
    is_anomaly = delta_pct >= data.price_threshold

    c1 = _check_hari_raya(data, today)
    c2 = _check_cuaca(data)
    c3 = _check_persebaran_kota(data)
    c4 = _check_stok(data)
    c5 = _check_inflasi_tren(data, today)
    c6 = _check_cross_commodity(data)
    checks = [c1, c2, c3, c4, c5, c6]

    # Diagnosis dari trigger pertama yang ditemukan
    # c4 "clear" = stok normal; c4 "triggered" = stok menipis/kritis
    if c1.status == "triggered":
        diagnosis = DiagnosisType.DEMAND
    elif c2.status == "triggered":
        diagnosis = DiagnosisType.SUPPLY
    elif c3.status == "triggered":
        diagnosis = DiagnosisType.SUPPLY
    elif c4.status == "triggered":
        diagnosis = DiagnosisType.UNKNOWN
    elif c5.status == "triggered":
        # Stok normal, tidak ada trigger supply/demand, tapi tren inflasi persisten
        diagnosis = DiagnosisType.EKSPEKTASI
    else:
        diagnosis = DiagnosisType.DISTRIBUSI

    return _build_result(data, diagnosis, checks, delta_pct, is_anomaly)


def _build_result(
    data: CommodityData,
    diagnosis: DiagnosisType,
    checks: list[CheckResult],
    delta_pct: float,
    is_anomaly: bool,
) -> RCAResult:
    tmpl = DIAGNOSIS_TEMPLATES[diagnosis]
    severity_level, yes_indicators = _score_severity(data, checks, delta_pct)
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
        severity_level=severity_level,
        yes_indicators=yes_indicators,
    )

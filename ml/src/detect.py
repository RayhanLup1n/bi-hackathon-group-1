"""
detect.py — Detection Engine (Lapis 2)
=======================================

Tiga modul deteksi:

A) HET Threshold Classification
   - green  : harga < 80% HET
   - yellow : 80% ≤ harga < 100% HET  (approaching limit)
   - red    : harga ≥ 100% HET        (breached)
   - Juga berlaku pada prediksi P90: jika pred_p90 > HET → pre-emptive alert

B) Online Change Point Detection
   - Lightweight: bandingkan mean 14 hari terakhir vs baseline 60 hari sebelumnya
   - Flag True jika pergeseran mean > N sigma (konfigurabel)
   - Tidak perlu ruptures untuk inference real-time; ruptures tersedia untuk
     analisis offline batch (detect_changepoints_offline)

C) Disparity Scoring
   - Skoring ketimpangan harga per komoditas antar kota
   - Basis: harga_ratio_nasional dari mart (sudah tersedia)
   - Score tinggi → kandidat wilayah untuk koordinasi stok

Semua fungsi pure (tidak ada state), cocok untuk unit testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from loguru import logger

AlertLevel = Literal["green", "yellow", "red", "unknown"]

# ── Thresholds (dapat di-override via config) ─────────────────────────────────

HET_YELLOW_THRESHOLD = 0.80   # 80% dari HET → masuk yellow zone
HET_RED_THRESHOLD    = 1.00   # 100% (tepat di HET atau di atas) → red
CP_SIGMA_THRESHOLD   = 2.0    # Z-score threshold untuk change point detection
CP_RECENT_WINDOW     = 14     # Hari terakhir untuk dianggap "recent"
CP_BASELINE_WINDOW   = 60     # Hari untuk baseline mean & std
CUSUM_SLACK          = 0.50   # k: allowable slack (units of σ); standar untuk seri ekonomi
CUSUM_THRESHOLD      = 4.00   # h: decision threshold (units of σ); ARL ≈ 370 pada h=4


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class HetAlertResult:
    """Hasil HET threshold check untuk satu komoditas-kota-tanggal."""
    komoditas_nama:     str
    kota_nama:          str
    tanggal:            date
    harga_aktual:       float
    het_harga:          float | None
    has_het:            bool
    alert_level:        AlertLevel
    jarak_ke_het_pct:   float | None    # (harga - het) / het * 100
    pred_p50:           float | None = None
    pred_p90:           float | None = None
    pred_alert_level:   AlertLevel = "unknown"   # alert berdasarkan prediksi P90


@dataclass
class ChangepointResult:
    """Hasil online change point detection."""
    komoditas_nama: str
    kota_nama:      str
    tanggal:        date
    is_changepoint: bool
    recent_mean:    float
    baseline_mean:  float
    sigma_shift:    float           # seberapa besar pergeseran dalam satuan std
    direction:      Literal["up", "down", "stable"]


@dataclass
class DisparityResult:
    """Hasil disparity scoring untuk satu komoditas pada tanggal tertentu."""
    komoditas_nama:     str
    tanggal:            date
    max_ratio:          float          # kota dengan harga tertinggi / nasional
    min_ratio:          float          # kota dengan harga terendah / nasional
    disparity_score:    float          # 0–1, semakin tinggi semakin timpang
    kota_termahal:      str
    kota_termurah:      str
    n_kota:             int


@dataclass
class CusumResult:
    """
    Hasil CUSUM (Cumulative Sum Control Chart) change point detection.

    CUSUM mendeteksi drift kumulatif yang kecil namun sustained — lebih awal 2–4 hari
    dibanding Z-score yang memerlukan spike tunggal besar. Ideal sebagai early warning
    sebelum harga benar-benar melanggar HET.
    """
    komoditas_nama: str
    kota_nama:      str
    tanggal:        date
    is_alarm:       bool          # True jika CUSUM melampaui decision threshold
    cusum_pos:      float         # Akumulator drift naik (CUSUM+)
    cusum_neg:      float         # Akumulator drift turun (CUSUM-)
    direction:      Literal["up", "down", "stable"]
    n_baseline:     int           # Jumlah observasi baseline yang digunakan


@dataclass
class DetectionResult:
    """Agregat semua sinyal deteksi untuk satu (komoditas, kota, tanggal)."""
    komoditas_nama:   str
    kota_nama:        str
    tanggal:          date
    het_alert:        HetAlertResult
    changepoint:      ChangepointResult | None   # Z-score: spike tunggal mendadak
    cusum:            CusumResult | None          # CUSUM: drift sustained (early warning)
    disparity:        DisparityResult | None
    # Composite final alert: escalate ke yang paling parah
    final_alert_level: AlertLevel = field(init=False)

    def __post_init__(self):
        # Z-score spike tunggal → red | CUSUM sustained drift → yellow (early warning)
        cp_alert    = "red"    if (self.changepoint and self.changepoint.is_changepoint) else "green"
        cusum_alert = "yellow" if (self.cusum and self.cusum.is_alarm)                  else "green"
        self.final_alert_level = _escalate_alert(
            self.het_alert.alert_level,
            self.het_alert.pred_alert_level,
            cp_alert,
            cusum_alert,
        )


# ── A) HET Threshold Classification ──────────────────────────────────────────

def classify_het_alert(
    harga_aktual: float,
    het_harga: float | None,
    *,
    yellow_threshold: float = HET_YELLOW_THRESHOLD,
    red_threshold: float = HET_RED_THRESHOLD,
) -> tuple[AlertLevel, float | None]:
    """
    Klasifikasi alert level berdasarkan perbandingan harga vs HET.

    Args:
        harga_aktual      : Harga aktual (Rupiah)
        het_harga         : HET (Rupiah), atau None jika tidak ada HET
        yellow_threshold  : Fraksi HET untuk masuk yellow (default: 0.80)
        red_threshold     : Fraksi HET untuk masuk red (default: 1.00)

    Returns:
        (alert_level, jarak_ke_het_pct)
        jarak_ke_het_pct: (harga - het) / het * 100. Positif = di atas HET.
    """
    if het_harga is None or np.isnan(het_harga) or het_harga <= 0:
        return "unknown", None

    ratio = harga_aktual / het_harga
    jarak_pct = (harga_aktual - het_harga) / het_harga * 100

    if ratio >= red_threshold:
        return "red", jarak_pct
    elif ratio >= yellow_threshold:
        return "yellow", jarak_pct
    else:
        return "green", jarak_pct


def build_het_alert(
    row: pd.Series,
    pred_p50: float | None = None,
    pred_p90: float | None = None,
) -> HetAlertResult:
    """Build HetAlertResult dari satu baris DataFrame + prediksi opsional."""
    het    = row.get("het_harga")
    has    = bool(row.get("has_het", False))
    harga  = float(row["harga_aktual"])

    alert_level, jarak_pct = classify_het_alert(harga, het if has else None)

    # Alert based on prediction P90
    pred_alert: AlertLevel = "unknown"
    if pred_p90 is not None and has and het:
        pred_alert, _ = classify_het_alert(pred_p90, het)

    return HetAlertResult(
        komoditas_nama   = str(row["komoditas_nama"]),
        kota_nama        = str(row["kota_nama"]),
        tanggal          = row["tanggal"],
        harga_aktual     = harga,
        het_harga        = float(het) if has else None,
        has_het          = has,
        alert_level      = alert_level,
        jarak_ke_het_pct = jarak_pct,
        pred_p50         = pred_p50,
        pred_p90         = pred_p90,
        pred_alert_level = pred_alert,
    )


# ── B) Change Point Detection ─────────────────────────────────────────────────

def detect_changepoint_online(
    recent_prices: np.ndarray | list[float],
    baseline_prices: np.ndarray | list[float],
    sigma_threshold: float = CP_SIGMA_THRESHOLD,
) -> tuple[bool, float, Literal["up", "down", "stable"]]:
    """
    Lightweight online change point detection.

    Membandingkan rata-rata recent window vs baseline window.
    Jika pergeseran > sigma_threshold standar deviasi baseline → changepoint.

    Args:
        recent_prices   : Harga N hari terakhir (array from [t-14, t])
        baseline_prices : Harga baseline (array from [t-74, t-15])
        sigma_threshold : Ambang batas z-score (default: 2.0)

    Returns:
        (is_changepoint, sigma_shift, direction)
    """
    recent   = np.array(recent_prices, dtype=float)
    baseline = np.array(baseline_prices, dtype=float)

    recent   = recent[~np.isnan(recent)]
    baseline = baseline[~np.isnan(baseline)]

    if len(recent) < 3 or len(baseline) < 7:
        return False, 0.0, "stable"

    baseline_mean = np.mean(baseline)
    baseline_std  = np.std(baseline)

    if baseline_std < 1:  # avoid division by near-zero
        baseline_std = 1.0

    recent_mean  = np.mean(recent)
    sigma_shift  = (recent_mean - baseline_mean) / baseline_std

    is_cp    = abs(sigma_shift) >= sigma_threshold
    direction: Literal["up", "down", "stable"]
    if sigma_shift >= sigma_threshold:
        direction = "up"
    elif sigma_shift <= -sigma_threshold:
        direction = "down"
    else:
        direction = "stable"

    return is_cp, float(sigma_shift), direction


def build_changepoint_result(
    komoditas_nama: str,
    kota_nama: str,
    tanggal: date,
    history_df: pd.DataFrame,
    recent_window: int = CP_RECENT_WINDOW,
    baseline_window: int = CP_BASELINE_WINDOW,
    sigma_threshold: float = CP_SIGMA_THRESHOLD,
) -> ChangepointResult | None:
    """
    Build ChangepointResult dari history DataFrame untuk satu (komoditas, kota).

    Args:
        history_df: DataFrame untuk SATU (comcat_id, kota_id), sudah sorted by tanggal.
                    Harus punya kolom: tanggal, harga_aktual.
    """
    if history_df.empty or len(history_df) < recent_window + 7:
        return None

    sorted_df = history_df.sort_values("tanggal")
    prices    = sorted_df["harga_aktual"].values

    # Ambil recent dan baseline windows
    if len(prices) < recent_window + baseline_window:
        recent   = prices[-recent_window:]
        baseline = prices[:-recent_window] if len(prices) > recent_window else prices[:1]
    else:
        recent   = prices[-recent_window:]
        baseline = prices[-(recent_window + baseline_window):-recent_window]

    is_cp, sigma_shift, direction = detect_changepoint_online(
        recent, baseline, sigma_threshold
    )

    return ChangepointResult(
        komoditas_nama = komoditas_nama,
        kota_nama      = kota_nama,
        tanggal        = tanggal,
        is_changepoint = is_cp,
        recent_mean    = float(np.nanmean(recent)),
        baseline_mean  = float(np.nanmean(baseline)),
        sigma_shift    = sigma_shift,
        direction      = direction,
    )


# ── B2) CUSUM Change Point Detection ─────────────────────────────────────────

def detect_changepoint_cusum(
    recent_prices: np.ndarray | list[float],
    baseline_prices: np.ndarray | list[float],
    slack: float = CUSUM_SLACK,
    threshold: float = CUSUM_THRESHOLD,
) -> tuple[bool, float, float, Literal["up", "down", "stable"]]:
    """
    CUSUM (Cumulative Sum Control Chart) untuk deteksi drift harga sustained.

    Berbeda dari Z-score yang mendeteksi spike tunggal besar, CUSUM mengakumulasi
    deviasi kecil dari baseline — sehingga dapat membunyikan alarm 2–4 hari lebih
    awal ketika harga bergerak perlahan namun konsisten ke atas/bawah.

    Algoritma:
        CUSUM+[t] = max(0, CUSUM+[t-1] + z[t] - k)   ← deteksi drift naik
        CUSUM-[t] = max(0, CUSUM-[t-1] - z[t] - k)   ← deteksi drift turun
        z[t] = (x[t] - μ_baseline) / σ_baseline
        Alarm ketika CUSUM+ > h atau CUSUM- > h

    Args:
        recent_prices   : Harga N hari terakhir (recent window)
        baseline_prices : Harga baseline (in-control period)
        slack           : k parameter — allowable slack sebelum akumulasi (default: 0.5σ)
        threshold       : h parameter — decision threshold (default: 4σ, ARL ≈ 370)

    Returns:
        (is_alarm, cusum_pos, cusum_neg, direction)
    """
    recent   = np.array(recent_prices,   dtype=float)
    baseline = np.array(baseline_prices, dtype=float)

    recent   = recent[~np.isnan(recent)]
    baseline = baseline[~np.isnan(baseline)]

    if len(baseline) < 7 or len(recent) < 3:
        return False, 0.0, 0.0, "stable"

    mu0    = float(np.mean(baseline))
    sigma0 = float(np.std(baseline))
    if sigma0 < 1.0:
        sigma0 = 1.0

    cusum_pos = 0.0
    cusum_neg = 0.0
    for x in recent:
        z = (x - mu0) / sigma0
        cusum_pos = max(0.0, cusum_pos + z - slack)
        cusum_neg = max(0.0, cusum_neg - z - slack)

    is_alarm = (cusum_pos > threshold) or (cusum_neg > threshold)

    direction: Literal["up", "down", "stable"]
    if cusum_pos > threshold:
        direction = "up"
    elif cusum_neg > threshold:
        direction = "down"
    else:
        direction = "stable"

    return is_alarm, cusum_pos, cusum_neg, direction


def build_cusum_result(
    komoditas_nama: str,
    kota_nama: str,
    tanggal: date,
    history_df: pd.DataFrame,
    recent_window: int = CP_RECENT_WINDOW,
    baseline_window: int = CP_BASELINE_WINDOW,
) -> CusumResult | None:
    """Build CusumResult dari history DataFrame untuk satu (komoditas, kota)."""
    if history_df.empty or len(history_df) < recent_window + 7:
        return None

    sorted_df = history_df.sort_values("tanggal")
    prices    = sorted_df["harga_aktual"].values

    if len(prices) < recent_window + baseline_window:
        recent   = prices[-recent_window:]
        baseline = prices[:-recent_window] if len(prices) > recent_window else prices[:1]
    else:
        recent   = prices[-recent_window:]
        baseline = prices[-(recent_window + baseline_window):-recent_window]

    is_alarm, cusum_pos, cusum_neg, direction = detect_changepoint_cusum(recent, baseline)

    return CusumResult(
        komoditas_nama = komoditas_nama,
        kota_nama      = kota_nama,
        tanggal        = tanggal,
        is_alarm       = is_alarm,
        cusum_pos      = float(cusum_pos),
        cusum_neg      = float(cusum_neg),
        direction      = direction,
        n_baseline     = len(baseline),
    )


def detect_changepoints_offline(
    df: pd.DataFrame,
    min_size: int = 14,
    n_bkps: int = 5,
) -> pd.DataFrame:
    """
    Offline batch change point detection menggunakan ruptures (Pelt algorithm).
    Jalankan sekali untuk seluruh dataset historis, hasilnya bisa di-visualisasi.

    Requires: pip install ruptures

    Args:
        df          : Full mart DataFrame (semua komoditas, kota, tanggal)
        min_size    : Minimum segment size
        n_bkps      : Maximum number of breakpoints per series

    Returns:
        DataFrame dengan kolom: comcat_id, kota_id, breakpoint_dates (list)
    """
    try:
        import ruptures as rpt
    except ImportError:
        logger.warning("ruptures tidak terinstall. Gunakan: pip install ruptures")
        return pd.DataFrame()

    results = []
    groups = df.groupby(["comcat_id", "kota_id"])

    for (comcat_id, kota_id), group in groups:
        series = group.sort_values("tanggal")["harga_aktual"].dropna().values

        if len(series) < min_size * 2:
            continue

        try:
            algo  = rpt.Pelt(model="rbf", min_size=min_size).fit(series)
            bkps  = algo.predict(pen=10)
            dates = group.sort_values("tanggal")["tanggal"].values
            bp_dates = [str(dates[b - 1]) for b in bkps if b - 1 < len(dates)]

            results.append({
                "comcat_id"       : comcat_id,
                "kota_id"         : kota_id,
                "breakpoint_dates": bp_dates,
                "n_breakpoints"   : len(bp_dates),
            })
        except Exception as e:
            logger.warning(f"CP detection failed for ({comcat_id}, {kota_id}): {e}")

    return pd.DataFrame(results)


# ── C) Disparity Scoring ──────────────────────────────────────────────────────

def compute_disparity(
    komoditas_nama: str,
    tanggal: date,
    kota_prices: dict[str, float],
) -> DisparityResult | None:
    """
    Hitung disparity score untuk satu komoditas pada satu tanggal.

    Args:
        kota_prices: {kota_nama: harga_aktual} untuk semua kota pada tanggal tersebut

    Disparity score = (max_ratio - min_ratio) / 2
    Range [0, 1] — semakin tinggi → semakin timpang distribusi harga antarkota.
    """
    if len(kota_prices) < 2:
        return None

    prices   = np.array(list(kota_prices.values()), dtype=float)
    kota_list = list(kota_prices.keys())
    nasional_mean = np.mean(prices)

    if nasional_mean <= 0:
        return None

    ratios = prices / nasional_mean
    max_idx = int(np.argmax(ratios))
    min_idx = int(np.argmin(ratios))

    disparity_score = float((ratios[max_idx] - ratios[min_idx]) / 2)

    return DisparityResult(
        komoditas_nama  = komoditas_nama,
        tanggal         = tanggal,
        max_ratio       = float(ratios[max_idx]),
        min_ratio       = float(ratios[min_idx]),
        disparity_score = min(disparity_score, 1.0),
        kota_termahal   = kota_list[max_idx],
        kota_termurah   = kota_list[min_idx],
        n_kota          = len(kota_list),
    )


def batch_disparity(
    df: pd.DataFrame,
    tanggal: date | str,
) -> dict[str, DisparityResult]:
    """
    Hitung disparity untuk semua komoditas pada satu tanggal.

    Returns:
        {komoditas_nama: DisparityResult}
    """
    df_day  = df[df["tanggal"] == pd.Timestamp(tanggal)]
    results = {}

    for komoditas, group in df_day.groupby("komoditas_nama"):
        kota_prices = dict(zip(group["kota_nama"], group["harga_aktual"]))
        result = compute_disparity(str(komoditas), date.fromisoformat(str(tanggal)), kota_prices)
        if result:
            results[str(komoditas)] = result

    return results


# ── Composite Alert Escalation ────────────────────────────────────────────────

_ALERT_RANK = {"green": 0, "yellow": 1, "red": 2, "unknown": -1}


def _escalate_alert(*levels: AlertLevel) -> AlertLevel:
    """Return the highest severity alert from a list."""
    valid = [l for l in levels if l in ("green", "yellow", "red")]
    if not valid:
        return "unknown"
    return max(valid, key=lambda x: _ALERT_RANK[x])


def run_detection(
    row: pd.Series,
    history_df: pd.DataFrame,
    day_df: pd.DataFrame,
    pred_p50: float | None = None,
    pred_p90: float | None = None,
) -> DetectionResult:
    """
    Jalankan semua 3 modul deteksi untuk satu (komoditas, kota, tanggal).

    Args:
        row        : Satu baris dari mart DataFrame
        history_df : History DataFrame untuk grup (comcat_id, kota_id) yang sama
        day_df     : Semua data untuk tanggal yang sama (untuk disparity)
        pred_p50   : Prediksi Q50 dari Lapis 1
        pred_p90   : Prediksi Q90 dari Lapis 1
    """
    komoditas = str(row["komoditas_nama"])
    kota      = str(row["kota_nama"])
    tanggal   = row["tanggal"]
    if isinstance(tanggal, pd.Timestamp):
        tanggal = tanggal.date()

    # A) HET alert
    het_alert = build_het_alert(row, pred_p50=pred_p50, pred_p90=pred_p90)

    # B1) Z-score change point (spike detection)
    changepoint = build_changepoint_result(komoditas, kota, tanggal, history_df)

    # B2) CUSUM (sustained drift — fires 2–4 days earlier than Z-score)
    cusum = build_cusum_result(komoditas, kota, tanggal, history_df)

    # C) Disparity
    kota_prices = dict(zip(day_df["kota_nama"], day_df["harga_aktual"]))
    disparity = compute_disparity(komoditas, tanggal, kota_prices)

    return DetectionResult(
        komoditas_nama = komoditas,
        kota_nama      = kota,
        tanggal        = tanggal,
        het_alert      = het_alert,
        changepoint    = changepoint,
        cusum          = cusum,
        disparity      = disparity,
    )

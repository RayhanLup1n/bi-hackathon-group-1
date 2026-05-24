"""
threat.py — FTA Threat Classifier for RADAR Pangan
====================================================

Implementasi 5-threat Fault Tree Analysis (FTA) evaluation dengan OR-gate logic.

Threats:
  T1: Hari raya / perayaan (demand spike — scheduled events)
  T2: Tekanan inflasi pangan (demand erosion / daya beli melemah)
  T3: Cuaca ekstrem di daerah produksi (supply disruption)
  T4: Defisit stok nasional (supply shortage — proxy metric)
  T5: Ketimpangan distribusi antarkota (spatial price disparity)

Siaga Level (OR-gate):
  aman     → 0 threats active
  waspada  → 1 threat active, severity < 0.5
  siaga    → 1 threat active (medium+) or 2 threats active
  kritis   → 3+ threats active or any threat severity >= 0.9
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from loguru import logger


# ── Thresholds ─────────────────────────────────────────────────────────────────

# T1: Hari raya demand window
T1_WINDOW_BEFORE         = 14    # hari sebelum event (H-14)
T1_WINDOW_AFTER          = 3     # hari setelah event (H+3)
T1_HIGH_IMPACT_KATEGORI  = {"islam", "nasional"}  # kategori dengan dampak harga tertinggi

# T2: Inflasi pangan (tekanan daya beli)
T2_MTM_THRESHOLD         = 2.0   # inflasi MtM >= 2% dianggap tekanan
T2_CONSECUTIVE_MONTHS    = 3     # berturut-turut >= T2_MTM_THRESHOLD

# T3: Cuaca ekstrem (derive dari precip_7d_avg & temp_max_7d di pipeline_cache)
T3_PRECIP_EKSTREM        = 50.0  # mm/hari rata-rata 7 hari → hujan lebat/banjir
T3_PRECIP_KERING         = 1.0   # mm/hari → kekeringan
T3_TEMP_EKSTREM          = 36.0  # °C rata-rata 7 hari → heat stress pada tanaman

# T4: Stok proxy (data Bapanas tidak tersedia)
T4_DISPARITY_RENDAH      = 0.10  # disparity_score rendah → semua kota naik bersamaan
T4_PCT_CHANGE_THRESHOLD  = 3.0   # % kenaikan harga 7 hari sebagai proxy supply stress

# T5: Ketimpangan distribusi
T5_DISPARITY_MIN         = 0.15  # disparity_score threshold


# ── Data Classes ────────────────────────────────────────────────────────────────

@dataclass
class ThreatResult:
    """Hasil evaluasi satu FTA threat."""
    threat_id:  str
    active:     bool | None    # True = aktif, False = tidak aktif, None = tidak diketahui
    evidence:   str            # penjelasan singkat (akan dikirim ke LLM)
    severity:   float = 0.0   # kekuatan sinyal 0.0–1.0
    label:      str   = ""    # human-readable label untuk frontend


@dataclass
class ThreatAssessment:
    """Hasil evaluasi semua 5 FTA threats dengan OR-gate scoring."""
    threats:         dict[str, ThreatResult] = field(default_factory=dict)
    active_count:    int   = 0
    severity_score:  float = 0.0    # sum severity dari threats yang aktif
    siaga_level:     str   = "aman" # 'aman'|'waspada'|'siaga'|'kritis'

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_count":   self.active_count,
            "severity_score": round(self.severity_score, 3),
            "siaga_level":    self.siaga_level,
            "threats": {
                tid: {
                    "active":   t.active,
                    "evidence": t.evidence,
                    "severity": round(t.severity, 3),
                    "label":    t.label,
                }
                for tid, t in self.threats.items()
            },
        }


# ── Classifier ─────────────────────────────────────────────────────────────────

class ThreatClassifier:
    """
    FTA Threat Classifier — evaluates all 5 threats untuk satu (komoditas, tanggal).

    Initialize sekali saat pipeline.load(), inject reference dataframes.
    Call evaluate_all() per request.
    """

    def __init__(
        self,
        df:             pd.DataFrame,
        df_hari_besar:  pd.DataFrame,
        df_musim_panen: pd.DataFrame,
        df_inflasi:     pd.DataFrame,
    ):
        self._df            = df
        self._hari_besar    = df_hari_besar.copy() if not df_hari_besar.empty else pd.DataFrame()
        self._musim_panen   = df_musim_panen
        self._inflasi       = df_inflasi

        if not self._hari_besar.empty and "tanggal" in self._hari_besar.columns:
            self._hari_besar["tanggal"] = pd.to_datetime(self._hari_besar["tanggal"])

        logger.info(
            f"ThreatClassifier initialized: "
            f"{len(self._hari_besar)} hari_besar | "
            f"{len(self._inflasi)} inflasi records | "
            f"{len(self._musim_panen)} musim_panen entries"
        )

    # ── Public Interface ──────────────────────────────────────────────────────

    def evaluate_all(
        self,
        tanggal:         date,
        row:             pd.Series,
        comcat_id:       str | None  = None,
        disparity_score: float | None = None,
    ) -> ThreatAssessment:
        """
        Evaluate semua 5 FTA threats.

        Args:
            tanggal:         Tanggal analisis
            row:             Satu baris dari pipeline_cache (30 feature cols + metadata)
            comcat_id:       ID komoditas (e.g. 'com_11') untuk lookup inflasi bulanan
            disparity_score: Disparity score dari Lapis 2 detection (opsional)
        """
        # Derive comcat_id dari row jika tidak diberikan
        if comcat_id is None and "comcat_id" in row.index:
            comcat_id = str(row["comcat_id"])

        results: dict[str, ThreatResult] = {
            "T1": self._eval_t1_hari_raya(tanggal),
            "T2": self._eval_t2_inflasi(tanggal, comcat_id),
            "T3": self._eval_t3_cuaca(row),
            "T4": self._eval_t4_stok_proxy(row, disparity_score),
            "T5": self._eval_t5_distribusi(disparity_score),
        }

        # OR-gate: hitung confirmed threats
        active_count   = sum(1 for t in results.values() if t.active is True)
        severity_score = sum(t.severity for t in results.values() if t.active is True)
        max_severity   = max((t.severity for t in results.values() if t.active is True), default=0.0)

        # Tentukan siaga level
        if active_count == 0:
            siaga_level = "aman"
        elif max_severity >= 0.9 or active_count >= 3:
            siaga_level = "kritis"
        elif active_count >= 2 or (active_count == 1 and severity_score >= 0.5):
            siaga_level = "siaga"
        else:
            siaga_level = "waspada"

        return ThreatAssessment(
            threats=results,
            active_count=active_count,
            severity_score=severity_score,
            siaga_level=siaga_level,
        )

    # ── Threat Evaluators ─────────────────────────────────────────────────────

    def _eval_t1_hari_raya(self, tanggal: date) -> ThreatResult:
        """T1: Demand spike karena hari raya / musim perayaan (window H-14 s/d H+3)."""
        if self._hari_besar.empty:
            return ThreatResult("T1", None, "Data hari_besar tidak tersedia", label="Hari Raya")

        t            = pd.Timestamp(tanggal)
        window_start = t - pd.Timedelta(days=T1_WINDOW_BEFORE)
        window_end   = t + pd.Timedelta(days=T1_WINDOW_AFTER)

        nearby = self._hari_besar[
            (self._hari_besar["tanggal"] >= window_start) &
            (self._hari_besar["tanggal"] <= window_end)
        ]

        if nearby.empty:
            return ThreatResult(
                "T1", False,
                f"Tidak ada hari besar dalam H-{T1_WINDOW_BEFORE}/H+{T1_WINDOW_AFTER}",
                severity=0.0, label="Hari Raya",
            )

        # Prioritaskan event dengan dampak tinggi (islam/nasional)
        high_impact = nearby[nearby["kategori"].isin(T1_HIGH_IMPACT_KATEGORI)]
        target      = high_impact.iloc[0] if not high_impact.empty else nearby.iloc[0]

        days_delta  = (pd.Timestamp(target["tanggal"]) - t).days
        days_abs    = abs(days_delta)
        severity    = max(0.2, 1.0 - days_abs / T1_WINDOW_BEFORE)
        if target["kategori"] not in T1_HIGH_IMPACT_KATEGORI:
            severity *= 0.5  # dampak lebih rendah untuk non-islam/nasional

        sign    = "+" if days_delta >= 0 else ""
        evidence = (
            f"{target['nama']} "
            f"(H{sign}{days_delta}, {target['tanggal'].strftime('%d %b %Y')})"
        )
        return ThreatResult("T1", True, evidence, severity=severity, label="Hari Raya")

    def _eval_t2_inflasi(self, tanggal: date, comcat_id: str | None) -> ThreatResult:
        """T2: Tekanan inflasi — inflasi MtM >= threshold selama N bulan berturut."""
        if self._inflasi.empty or comcat_id is None:
            return ThreatResult("T2", None, "Data inflasi tidak tersedia", label="Tekanan Inflasi")

        inf_sub = self._inflasi[self._inflasi["komoditas_id"] == comcat_id]
        if inf_sub.empty:
            return ThreatResult(
                "T2", None,
                f"Data inflasi tidak ditemukan untuk komoditas {comcat_id}",
                label="Tekanan Inflasi",
            )

        # Bangun list (tahun, bulan) untuk N bulan terakhir
        months: list[tuple[int, int]] = []
        y, m = tanggal.year, tanggal.month
        for _ in range(T2_CONSECUTIVE_MONTHS):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        # Cek streak inflasi tinggi (dari bulan paling baru ke paling lama)
        consecutive_high = 0
        mtm_values: list[float] = []

        for yr, mn in months:
            row_inf = inf_sub[(inf_sub["tahun"] == yr) & (inf_sub["bulan"] == mn)]
            if row_inf.empty:
                break  # data tidak ada → hentikan streak check
            mtm = float(row_inf.iloc[0]["inflasi_mtm"])
            mtm_values.append(mtm)
            if mtm >= T2_MTM_THRESHOLD:
                consecutive_high += 1
            else:
                break  # streak terputus

        if consecutive_high >= T2_CONSECUTIVE_MONTHS:
            avg_mtm  = sum(mtm_values[:T2_CONSECUTIVE_MONTHS]) / T2_CONSECUTIVE_MONTHS
            severity = min(1.0, avg_mtm / 10.0)
            evidence = (
                f"Inflasi MtM ≥{T2_MTM_THRESHOLD}% selama {consecutive_high} bulan berturut "
                f"(rata-rata: {avg_mtm:.1f}%)"
            )
            return ThreatResult("T2", True, evidence, severity=severity, label="Tekanan Inflasi")

        latest_mtm = mtm_values[0] if mtm_values else 0.0
        evidence   = (
            f"Inflasi MtM bulan ini: {latest_mtm:.1f}% "
            f"(butuh ≥{T2_MTM_THRESHOLD}% selama {T2_CONSECUTIVE_MONTHS} bulan berturut)"
        )
        return ThreatResult("T2", False, evidence, severity=0.0, label="Tekanan Inflasi")

    def _eval_t3_cuaca(self, row: pd.Series) -> ThreatResult:
        """T3: Cuaca ekstrem (derive dari precip_7d_avg + temp_max_7d di pipeline_cache)."""
        precip = float(row.get("precip_7d_avg", float("nan")))
        temp   = float(row.get("temp_max_7d",   float("nan")))

        if pd.isna(precip) or pd.isna(temp):
            return ThreatResult("T3", None, "Data cuaca tidak tersedia di pipeline", label="Cuaca Ekstrem")

        signals:  list[str]  = []
        severity: float      = 0.0

        # Hujan lebat / banjir
        if precip >= T3_PRECIP_EKSTREM:
            sev = min(1.0, precip / 100.0)
            severity = max(severity, sev)
            signals.append(f"Curah hujan {precip:.1f}mm/hari (ekstrem, ambang {T3_PRECIP_EKSTREM}mm)")

        # Kekeringan
        elif precip <= T3_PRECIP_KERING:
            sev = max(0.3, (T3_PRECIP_KERING - precip) / T3_PRECIP_KERING)
            severity = max(severity, sev)
            signals.append(f"Curah hujan {precip:.1f}mm/hari (kekeringan, ambang {T3_PRECIP_KERING}mm)")

        # Suhu panas ekstrem
        if temp >= T3_TEMP_EKSTREM:
            sev = min(1.0, (temp - T3_TEMP_EKSTREM) / 5.0)
            severity = max(severity, sev)
            signals.append(f"Suhu {temp:.1f}°C rata-rata 7 hari (heat stress, ambang {T3_TEMP_EKSTREM}°C)")

        if signals:
            return ThreatResult(
                "T3", True, "; ".join(signals),
                severity=severity, label="Cuaca Ekstrem",
            )
        return ThreatResult(
            "T3", False,
            f"Cuaca normal — precip: {precip:.1f}mm/hari, suhu: {temp:.1f}°C",
            severity=0.0, label="Cuaca Ekstrem",
        )

    def _eval_t4_stok_proxy(
        self,
        row:             pd.Series,
        disparity_score: float | None,
    ) -> ThreatResult:
        """
        T4: Defisit stok nasional (proxy — data Bapanas tidak tersedia).

        Logic: harga naik di SEMUA kota bersamaan (disparity rendah) +
        kenaikan % besar = kemungkinan defisit supply nasional, bukan sekadar
        masalah distribusi (T5).
        """
        pct_change = float(row.get("pct_change_7d", 0.0) or 0.0)

        # Proxy kuat: disparity rendah (semua kota naik) + harga naik signifikan
        if (
            disparity_score is not None
            and disparity_score < T4_DISPARITY_RENDAH
            and pct_change >= T4_PCT_CHANGE_THRESHOLD
        ):
            severity = min(0.6, pct_change / 15.0)  # cap 0.6 karena hanya proxy
            evidence = (
                f"Proxy defisit stok: harga naik {pct_change:+.1f}% (7 hari) "
                f"dengan disparitas rendah ({disparity_score:.3f}) → kemungkinan shortage nasional "
                f"(data Bapanas tidak tersedia)"
            )
            return ThreatResult("T4", True, evidence, severity=severity, label="Defisit Stok")

        # Data tidak cukup untuk konfirmasi
        evidence = (
            f"Data stok Bapanas tidak tersedia — "
            f"proxy: Δharga 7 hari = {pct_change:+.1f}%"
        )
        return ThreatResult("T4", None, evidence, severity=0.0, label="Defisit Stok")

    def _eval_t5_distribusi(self, disparity_score: float | None) -> ThreatResult:
        """T5: Ketimpangan distribusi antarkota (harga naik hanya di sebagian kota)."""
        if disparity_score is None or pd.isna(disparity_score):
            return ThreatResult("T5", None, "Data disparitas tidak tersedia", label="Distribusi")

        disparity_score = float(disparity_score)

        if disparity_score >= T5_DISPARITY_MIN:
            severity = min(1.0, disparity_score / 0.5)
            evidence = (
                f"Disparitas harga antarkota: {disparity_score:.3f} "
                f"(ambang: {T5_DISPARITY_MIN}) → ketimpangan distribusi terdeteksi"
            )
            return ThreatResult("T5", True, evidence, severity=severity, label="Distribusi")

        return ThreatResult(
            "T5", False,
            f"Distribusi normal — disparitas: {disparity_score:.3f}",
            severity=0.0, label="Distribusi",
        )

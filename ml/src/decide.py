"""
decide.py — LLM Reasoning Agent (Lapis 3 — Decision Engine)
============================================================

Pattern: ReAct (Reason + Act) menggunakan OpenAI function calling.
Model default: gpt-4o-mini (murah, cepat, cukup untuk structured reasoning).

Flow:
  1. Kumpulkan sinyal dari Lapis 1 (prediksi) dan Lapis 2 (detection)
  2. Build context prompt
  3. Jalankan ReAct loop:
       - LLM reasoning → pilih tool
       - Execute tool (query dari in-memory DataFrame context)
       - Feed result kembali ke LLM
       - Ulangi sampai LLM give final answer (no tool call)
  4. Parse dan return DecisionResult

Tools yang tersedia:
  - get_historical_pattern   : pola musiman harga per komoditas-bulan
  - compare_regional_prices  : perbandingan harga per kota untuk komoditas tertentu
  - get_upcoming_events      : event musiman yang akan datang (Ramadan, tahun baru, dll)
  - get_het_breach_history   : frekuensi pelanggaran HET N hari terakhir

Fallback:
  Jika OpenAI API tidak tersedia atau gagal, gunakan rule-based fallback
  yang scoring sederhana tanpa LLM.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd
from loguru import logger

from ml.src.detect import AlertLevel, DetectionResult

# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class DecisionResult:
    """Output final dari Lapis 3 Decision Engine."""
    komoditas_nama:       str
    kota_nama:            str
    tanggal:              date
    final_alert_level:    AlertLevel
    intervention_priority: int            # 1 = paling urgent, 5 = rendah
    rekomendasi:          str             # 2-3 kalimat, Bahasa Indonesia, actionable
    reasoning_trace:      list[str]       # Chain of thought dari agent
    tools_called:         list[str]       # List tool names yang dipanggil
    confidence:           Literal["high", "medium", "low"]
    is_llm_generated:     bool            # True = LLM, False = rule-based fallback


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Kamu adalah RADAR Pangan Intervention Agent — agen rekomendasi intervensi inflasi pangan \
yang expert di kebijakan harga pangan Indonesia.

TUGAS KAMU:
Berdasarkan data harga aktual, prediksi ML, dan sinyal deteksi, kamu harus:
1. Tentukan final_alert_level: "green", "yellow", atau "red"
2. Tentukan intervention_priority: angka 1–5 (1 = paling mendesak)
3. Tulis rekomendasi: 2-3 kalimat spesifik dan actionable dalam Bahasa Indonesia
4. Catat reasoning kamu (singkat)

ATURAN KEPUTUSAN:
- Selalu gunakan minimal SATU tool sebelum memutuskan
- Jika prediksi P90 sudah melampaui HET → minimal yellow
- Jika ada changepoint DAN prediksi breaches HET → red
- Jika is_cusum_alarm=true → indikasi drift harga sustained (early warning); rekomendasikan tindakan preventif
- Jika is_changepoint=true DAN is_cusum_alarm=true → konfirmasi kuat adanya regime change harga → prioritas tinggi
- Pertimbangkan konteks musiman (Ramadan, tahun baru, musim panen)
- Rekomendasi harus spesifik: sebutkan instrumen intervensi \
  (operasi pasar, koordinasi stok antardaerah, sidak harga, usulan peningkatan pasokan)
- Jika ada wilayah surplus teridentifikasi → rekomendasikan koordinasi stok ke wilayah defisit. Sebutkan hingga 2 kota sumber (dari 'top3_surplus_terdekat') jika tersedia, beserta estimasi selisih harganya.
- Untuk redistribusi stok: HANYA sebutkan kota yang muncul di field 'kota_surplus_terdekat' atau 'top3_surplus_terdekat'. Tool sudah menyaring — kota yang tidak ada di daftar itu berarti terlalu jauh (beda pulau) dan TIDAK BOLEH disebut dalam rekomendasi. Jika 'kota_surplus_terdekat' null, rekomendasikan operasi pasar lokal saja.
- LARANGAN KERAS: JANGAN PERNAH menyebut nama kota berdasarkan pengetahuan kamu sendiri. Kamu HANYA boleh menyebut kota yang secara eksplisit tertulis di hasil tool call. Jika kota tidak ada di output tool, kota itu tidak boleh muncul di rekomendasi dalam bentuk apapun — termasuk "jika logistik memungkinkan" atau frasa bersyarat lainnya.
- Jangan hanya bilang "pantau terus" — itu bukan rekomendasi actionable

FORMAT JAWABAN AKHIR (JSON):
{
  "final_alert_level": "green"|"yellow"|"red",
  "intervention_priority": 1-5,
  "rekomendasi": "...",
  "reasoning": "...",
  "confidence": "high"|"medium"|"low"
}
""".strip()


# ── Tool Definitions (OpenAI function schema) ─────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_historical_pattern",
            "description": (
                "Dapatkan pola historis harga per bulan untuk komoditas tertentu. "
                "Berguna untuk menilai apakah kenaikan harga saat ini normal secara musiman."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "komoditas_nama": {
                        "type": "string",
                        "description": "Nama komoditas persis seperti di database"
                    },
                    "bulan": {
                        "type": "integer",
                        "description": "Bulan (1-12) yang ingin dilihat polanya"
                    },
                },
                "required": ["komoditas_nama", "bulan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_regional_prices",
            "description": (
                "Bandingkan harga komoditas di semua kota pada tanggal tertentu. "
                "Berguna untuk identifikasi wilayah surplus (harga rendah) dan defisit (harga tinggi). "
                "Hasil hanya berisi kota di pulau yang sama atau bertetangga dengan kota target. "
                "Gunakan 'kota_surplus_terdekat' atau 'top3_surplus_terdekat' untuk rekomendasi redistribusi stok. "
                "JANGAN sebutkan kota lain di luar daftar tersebut — kota yang tidak tampil berarti terlalu jauh."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "komoditas_nama": {
                        "type": "string",
                        "description": "Nama komoditas"
                    },
                    "tanggal": {
                        "type": "string",
                        "description": "Tanggal dalam format YYYY-MM-DD"
                    },
                },
                "required": ["komoditas_nama", "tanggal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_events",
            "description": (
                "Dapatkan daftar event musiman yang akan datang dalam 30 hari ke depan "
                "(Ramadan, Lebaran, tahun baru, musim panen) beserta dampak historis ke harga."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tanggal_referensi": {
                        "type": "string",
                        "description": "Tanggal referensi untuk menghitung 30 hari ke depan (YYYY-MM-DD)"
                    },
                },
                "required": ["tanggal_referensi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_het_breach_history",
            "description": (
                "Dapatkan frekuensi historis pelanggaran HET untuk komoditas dan kota tertentu "
                "dalam N hari terakhir. Berguna untuk menilai apakah ini anomali atau pola berulang."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "komoditas_nama": {"type": "string"},
                    "kota_nama":      {"type": "string"},
                    "lookback_days":  {"type": "integer", "default": 90},
                },
                "required": ["komoditas_nama", "kota_nama"],
            },
        },
    },
]


# ── Tool Implementations (query in-memory DataFrames) ─────────────────────────

class ToolContext:
    """
    Menyimpan DataFrame context untuk tools.
    Disiapkan sekali per analisis batch, lalu dipass ke ReasoningAgent.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        df_hari_besar: pd.DataFrame | None = None,
        df_musim_panen: pd.DataFrame | None = None,
    ):
        """
        Args:
            df             : Full feature DataFrame (dari build_feature_dataset) dengan kolom
                             tanggal, komoditas_nama, kota_nama, harga_aktual, het_harga, has_het, bulan
            df_hari_besar  : DataFrame dari app.hari_besar (kolom: tanggal, nama, kategori)
            df_musim_panen : DataFrame dari app.musim_panen (kolom: komoditas_nama, bulan_mulai,
                             bulan_selesai, daerah_utama, catatan)
        """
        self.df             = df
        self.df_hari_besar  = df_hari_besar  if df_hari_besar  is not None else pd.DataFrame()
        self.df_musim_panen = df_musim_panen if df_musim_panen is not None else pd.DataFrame()
        self._target_pulau: str = "unknown"  # set per-request by ReasoningAgent.decide()

    def get_historical_pattern(self, komoditas_nama: str, bulan: int) -> dict[str, Any]:
        """Statistik harga per bulan untuk komoditas tertentu."""
        mask  = (
            (self.df["komoditas_nama"] == komoditas_nama) &
            (self.df["bulan"] == bulan)
        )
        sub   = self.df[mask]["harga_aktual"].dropna()

        if sub.empty:
            return {"error": f"Tidak ada data untuk {komoditas_nama} bulan {bulan}"}

        # Historical average for the same month excluding recent year
        latest_year = self.df["tanggal"].max()
        if hasattr(latest_year, "year"):
            latest_year = latest_year.year
        else:
            latest_year = pd.Timestamp(latest_year).year

        hist_mask = mask & (pd.to_datetime(self.df["tanggal"]).dt.year < latest_year)
        hist_sub  = self.df[hist_mask]["harga_aktual"].dropna()

        result = {
            "komoditas_nama": komoditas_nama,
            "bulan": bulan,
            "total_records": len(sub),
            "rata_rata_harga_bulan_ini": round(float(sub.mean()), 0),
            "std_harga": round(float(sub.std()), 0),
            "min_harga": round(float(sub.min()), 0),
            "max_harga": round(float(sub.max()), 0),
        }

        if len(hist_sub) >= 30:
            result["rata_rata_historis_bulan_sama"] = round(float(hist_sub.mean()), 0)
            result["pct_change_vs_historis"] = round(
                (float(sub.mean()) - float(hist_sub.mean())) / float(hist_sub.mean()) * 100, 1
            )
            result["interpretasi"] = (
                "Di atas rata-rata historis" if result["pct_change_vs_historis"] > 5
                else "Normal" if abs(result["pct_change_vs_historis"]) <= 5
                else "Di bawah rata-rata historis"
            )

        return result

    # ── Island proximity helpers ───────────────────────────────────────────────

    # Maps provinsi_nama keyword → pulau (island group)
    _PROVINSI_TO_PULAU: dict[str, str] = {
        "DKI Jakarta": "Jawa", "Jawa Barat": "Jawa", "Jawa Tengah": "Jawa",
        "Jawa Timur": "Jawa", "DI Yogyakarta": "Jawa", "Banten": "Jawa",
        "Aceh": "Sumatra", "Sumatera Utara": "Sumatra", "Sumatera Barat": "Sumatra",
        "Riau": "Sumatra", "Kepulauan Riau": "Sumatra", "Jambi": "Sumatra",
        "Sumatera Selatan": "Sumatra", "Bangka Belitung": "Sumatra",
        "Bengkulu": "Sumatra", "Lampung": "Sumatra",
        "Kalimantan Barat": "Kalimantan", "Kalimantan Tengah": "Kalimantan",
        "Kalimantan Selatan": "Kalimantan", "Kalimantan Timur": "Kalimantan",
        "Kalimantan Utara": "Kalimantan",
        "Sulawesi Utara": "Sulawesi", "Sulawesi Tengah": "Sulawesi",
        "Sulawesi Selatan": "Sulawesi", "Sulawesi Tenggara": "Sulawesi",
        "Sulawesi Barat": "Sulawesi", "Gorontalo": "Sulawesi",
        "Bali": "Bali",
        "Nusa Tenggara Barat": "NTB", "Nusa Tenggara Timur": "NTT",
        "Maluku": "Maluku", "Maluku Utara": "Maluku",
        "Papua": "Papua", "Papua Barat": "Papua", "Papua Selatan": "Papua",
        "Papua Tengah": "Papua", "Papua Pegunungan": "Papua",
    }

    # Neighboring island pairs (undirected)
    _PULAU_NEIGHBORS: dict[str, set[str]] = {
        "Jawa":       {"Sumatra", "Bali"},
        "Sumatra":    {"Jawa", "Kalimantan"},
        "Bali":       {"Jawa", "NTB"},
        "NTB":        {"Bali", "NTT"},
        "NTT":        {"NTB"},
        "Kalimantan": {"Sumatra", "Sulawesi"},
        "Sulawesi":   {"Kalimantan", "Maluku"},
        "Maluku":     {"Sulawesi", "Papua"},
        "Papua":      {"Maluku"},
    }

    def _get_pulau(self, provinsi_nama: str) -> str:
        """Return island group for a province name."""
        for key, pulau in self._PROVINSI_TO_PULAU.items():
            if key.lower() in str(provinsi_nama).lower():
                return pulau
        return "unknown"

    def _proximity(self, pulau_target: str, pulau_other: str) -> str:
        """Return proximity label from target island to another island."""
        if pulau_target == "unknown" or pulau_other == "unknown":
            return "unknown"
        if pulau_target == pulau_other:
            return "same_island"
        if pulau_other in self._PULAU_NEIGHBORS.get(pulau_target, set()):
            return "neighboring"
        return "far"

    def compare_regional_prices(self, komoditas_nama: str, tanggal: str) -> dict[str, Any]:
        """Perbandingan harga per kota untuk komoditas pada tanggal tertentu,
        dengan informasi proximity (kedekatan geografis) ke kota target."""
        ts   = pd.Timestamp(tanggal)
        cols = ["kota_nama", "provinsi_nama", "harga_aktual", "harga_ratio_nasional"]
        # keep only cols that actually exist in df
        cols = [c for c in cols if c in self.df.columns]

        mask = (
            (self.df["komoditas_nama"] == komoditas_nama) &
            (pd.to_datetime(self.df["tanggal"]) == ts)
        )
        sub  = self.df[mask][cols].dropna(subset=["harga_aktual"])

        if sub.empty:
            # Try nearest date within 7 days
            t_pd   = pd.to_datetime(self.df["tanggal"])
            nearby = self.df[
                (self.df["komoditas_nama"] == komoditas_nama) &
                (t_pd >= ts - pd.Timedelta(days=7)) &
                (t_pd <= ts)
            ]
            if nearby.empty:
                return {"error": f"Tidak ada data regional untuk {komoditas_nama} sekitar {tanggal}"}
            latest = nearby.sort_values("tanggal").groupby("kota_nama").last().reset_index()
            sub  = latest[cols].dropna(subset=["harga_aktual"])

        nasional_mean = float(sub["harga_aktual"].mean())
        rows = sub.sort_values("harga_aktual", ascending=False)

        # Determine target city's island from the analysis context.
        # We approximate by looking at what city was queried — not available here directly,
        # so we use a session-level hint stored at __init__ time (see _target_pulau).
        target_pulau = getattr(self, "_target_pulau", "unknown")

        kota_list = []
        for _, r in rows.iterrows():
            provinsi = r.get("provinsi_nama", "") if "provinsi_nama" in r.index else ""
            pulau    = self._get_pulau(str(provinsi))
            is_surplus = r["harga_aktual"] < nasional_mean * 0.95
            is_defisit = r["harga_aktual"] > nasional_mean * 1.05
            kota_list.append({
                "kota": r["kota_nama"],
                "provinsi": provinsi,
                "pulau": pulau,
                "proximity_ke_target": self._proximity(target_pulau, pulau),
                "harga": int(r["harga_aktual"]),
                "ratio_vs_nasional": round(float(r.get("harga_ratio_nasional") or
                                                  r["harga_aktual"] / nasional_mean), 3),
                "status": "surplus (harga rendah)" if is_surplus
                          else "defisit (harga tinggi)" if is_defisit
                          else "normal",
            })

        # Only keep same_island + neighboring — never expose far entries to LLM
        nearby_surplus = [
            k for k in kota_list
            if k["status"] == "surplus (harga rendah)"
            and k["proximity_ke_target"] in ("same_island", "neighboring")
        ]
        nearby_surplus_sorted = sorted(
            nearby_surplus,
            key=lambda k: (0 if k["proximity_ke_target"] == "same_island" else 1, k["harga"])
        )

        nearby_kota = [
            k for k in kota_list
            if k["proximity_ke_target"] in ("same_island", "neighboring")
        ]

        # Termahal among nearby only
        nearby_kota_by_price = sorted(nearby_kota, key=lambda k: k["harga"], reverse=True)

        return {
            "komoditas_nama": komoditas_nama,
            "tanggal": tanggal,
            "rata_rata_nasional": int(nasional_mean),
            "kota_termahal_terdekat": nearby_kota_by_price[0] if nearby_kota_by_price else None,
            "kota_surplus_terdekat": nearby_surplus_sorted[0] if nearby_surplus_sorted else None,
            "top3_surplus_terdekat": nearby_surplus_sorted[:3],
            "catatan": (
                "Hanya kota pulau yang sama atau bertetangga ditampilkan. "
                "JANGAN sebutkan kota lain di luar daftar ini dalam rekomendasi."
            ),
            "semua_kota_terdekat": nearby_kota,
        }

    def get_upcoming_events(self, tanggal_referensi: str) -> dict[str, Any]:
        """Event musiman dalam 30 hari ke depan: hari besar nasional dan musim panen."""
        ref    = date.fromisoformat(tanggal_referensi)
        end    = ref + timedelta(days=30)
        events: list[dict[str, Any]] = []

        # ── 1. Hari Besar Nasional from DB ────────────────────────────────────
        if not self.df_hari_besar.empty:
            df_hb = self.df_hari_besar.copy()
            df_hb["tanggal"] = pd.to_datetime(df_hb["tanggal"]).dt.date
            upcoming = df_hb[
                (df_hb["tanggal"] > ref) & (df_hb["tanggal"] <= end)
            ].sort_values("tanggal")

            for _, row in upcoming.iterrows():
                hari_ke_depan = (row["tanggal"] - ref).days
                events.append({
                    "jenis":             "hari_besar",
                    "event":             row.get("nama", "Hari Besar Nasional"),
                    "kategori":          row.get("kategori", ""),
                    "tanggal":           str(row["tanggal"]),
                    "hari_ke_depan":     hari_ke_depan,
                    "dampak_harga":      "+10–25% untuk bawang dan cabai pada H-7 s/d H+3",
                    "catatan":           "Sumber: app.hari_besar (python-holidays 2024–2027)",
                })
        else:
            # Fallback: proxy Ramadan/Lebaran (bulan 3–5) dan Natal/Tahun Baru
            for offset in range(1, 31):
                d = ref + timedelta(days=offset)
                if d.month in (3, 4, 5):
                    events.append({
                        "jenis":         "hari_besar",
                        "event":         "Musim Ramadan/Lebaran (proxy)",
                        "tanggal":       str(date(d.year, 3, 1)),
                        "hari_ke_depan": (date(d.year, 3, 1) - ref).days,
                        "dampak_harga":  "+15–30% untuk cabai, bawang",
                        "catatan":       "Proxy bulan 3-5; tidak ada data hari_besar di DB",
                    })
                    break
            for offset in range(1, 31):
                d = ref + timedelta(days=offset)
                if d.month == 12 and d.day >= 20:
                    events.append({
                        "jenis":         "hari_besar",
                        "event":         "Libur Natal & Tahun Baru (proxy)",
                        "tanggal":       str(d),
                        "hari_ke_depan": offset,
                        "dampak_harga":  "+5–15% untuk daging, telur, sayuran",
                        "catatan":       "Proxy; tidak ada data hari_besar di DB",
                    })
                    break

        # ── 2. Musim Panen from DB ────────────────────────────────────────────
        if not self.df_musim_panen.empty:
            # Compute which months fall in the 30-day window
            months_in_window: set[int] = set()
            for offset in range(0, 31):
                months_in_window.add((ref + timedelta(days=offset)).month)

            for _, row in self.df_musim_panen.iterrows():
                try:
                    b_mulai    = int(row["bulan_mulai"])
                    b_selesai  = int(row["bulan_selesai"])
                except (ValueError, TypeError):
                    continue

                if b_mulai <= b_selesai:
                    season_months = set(range(b_mulai, b_selesai + 1))
                else:                          # wraps across December → January
                    season_months = set(range(b_mulai, 13)) | set(range(1, b_selesai + 1))

                if months_in_window & season_months:
                    events.append({
                        "jenis":         "musim_panen",
                        "event":         f"Musim Panen: {row.get('komoditas_nama', '')}",
                        "daerah_utama":  row.get("daerah_utama", ""),
                        "bulan_mulai":   b_mulai,
                        "bulan_selesai": b_selesai,
                        "dampak_harga":  "Harga cenderung turun 10–20% saat panen raya di daerah produksi",
                        "catatan":       row.get("catatan", ""),
                    })

        if not events:
            events.append({
                "jenis":         "none",
                "event":         "Tidak ada event besar dalam 30 hari ke depan",
                "hari_ke_depan": None,
                "dampak_harga":  "Normal seasonality",
            })

        return {
            "tanggal_referensi": tanggal_referensi,
            "window_hari":       30,
            "total_events":      len(events),
            "events":            events,
        }

    def get_het_breach_history(
        self,
        komoditas_nama: str,
        kota_nama: str,
        lookback_days: int = 90,
    ) -> dict[str, Any]:
        """Frekuensi pelanggaran HET N hari terakhir."""
        if "has_het" not in self.df.columns or "jarak_ke_het_pct" not in self.df.columns:
            return {"error": "Data HET belum di-join. Jalankan add_het_features() dulu."}

        t_latest = pd.to_datetime(self.df["tanggal"]).max()
        t_start  = t_latest - pd.Timedelta(days=lookback_days)

        mask = (
            (self.df["komoditas_nama"] == komoditas_nama) &
            (self.df["kota_nama"] == kota_nama) &
            (pd.to_datetime(self.df["tanggal"]) >= t_start) &
            (self.df["has_het"] == True)
        )
        sub = self.df[mask].dropna(subset=["jarak_ke_het_pct"])

        if sub.empty:
            return {"error": f"Tidak ada data HET untuk {komoditas_nama} di {kota_nama}"}

        n_total   = len(sub)
        n_breach  = int((sub["jarak_ke_het_pct"] >= 0).sum())
        n_warning = int(
            ((sub["jarak_ke_het_pct"] >= -20) & (sub["jarak_ke_het_pct"] < 0)).sum()
        )

        return {
            "komoditas_nama": komoditas_nama,
            "kota_nama": kota_nama,
            "lookback_hari": lookback_days,
            "total_hari_data": n_total,
            "hari_breach_het": n_breach,
            "pct_breach": round(n_breach / n_total * 100, 1),
            "hari_warning_zone": n_warning,
            "rata_rata_jarak_het_pct": round(float(sub["jarak_ke_het_pct"].mean()), 1),
            "interpretasi": (
                "Pelanggaran kronis (>30% hari)" if n_breach / n_total > 0.3
                else "Pelanggaran sesekali" if n_breach > 0
                else "Belum pernah melanggar HET dalam periode ini"
            ),
        }

    def call(self, tool_name: str, args: dict[str, Any]) -> str:
        """Dispatch tool call dan return JSON string hasil."""
        try:
            if tool_name == "get_historical_pattern":
                result = self.get_historical_pattern(**args)
            elif tool_name == "compare_regional_prices":
                result = self.compare_regional_prices(**args)
            elif tool_name == "get_upcoming_events":
                result = self.get_upcoming_events(**args)
            elif tool_name == "get_het_breach_history":
                result = self.get_het_breach_history(**args)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            result = {"error": str(e)}

        return json.dumps(result, ensure_ascii=False, default=str)


# ── Rule-Based Fallback (no LLM) ─────────────────────────────────────────────

def _rule_based_decision(detection: DetectionResult, df_context: pd.DataFrame) -> DecisionResult:
    """
    Fallback tanpa LLM. Gunakan multi-criteria scoring sederhana.
    Dipakai ketika OpenAI API tidak tersedia / timeout.
    """
    h = detection.het_alert
    cp = detection.changepoint
    disp = detection.disparity

    # Score components [0-1]
    het_score = (
        1.0 if h.alert_level == "red"
        else 0.6 if h.alert_level == "yellow"
        else 0.0
    )
    pred_score = (
        1.0 if h.pred_alert_level == "red"
        else 0.5 if h.pred_alert_level == "yellow"
        else 0.0
    )
    cp_score   = 0.4 if (cp and cp.is_changepoint) else 0.0
    disp_score = (disp.disparity_score * 0.3) if disp else 0.0

    composite = het_score * 0.4 + pred_score * 0.3 + cp_score * 0.2 + disp_score * 0.1

    final_alert: AlertLevel
    if composite >= 0.7:
        final_alert = "red"
        priority    = 1
    elif composite >= 0.4:
        final_alert = "yellow"
        priority    = 3
    else:
        final_alert = "green"
        priority    = 5

    # Build recommendation text
    parts = []
    if h.has_het and h.jarak_ke_het_pct is not None:
        gap_pct = abs(h.jarak_ke_het_pct)
        if h.alert_level == "red":
            parts.append(
                f"Harga {h.komoditas_nama} di {h.kota_nama} sudah {gap_pct:.1f}% di atas HET."
            )
        elif h.alert_level == "yellow":
            parts.append(
                f"Harga {h.komoditas_nama} di {h.kota_nama} berada di {100 - gap_pct:.0f}% "
                f"dari batas HET."
            )

    if cp and cp.is_changepoint:
        parts.append(
            f"Terdeteksi perubahan regime harga mendadak ({cp.direction}, "
            f"{abs(cp.sigma_shift):.1f}σ dari baseline)."
        )

    if disp and disp.disparity_score > 0.15:
        parts.append(
            f"Disparitas harga antarkota signifikan — koordinasi stok ke {disp.kota_termahal} direkomendasikan."
        )

    if not parts:
        parts.append(f"Harga {h.komoditas_nama} di {h.kota_nama} dalam kondisi normal.")

    rekomendasi = " ".join(parts)

    return DecisionResult(
        komoditas_nama        = h.komoditas_nama,
        kota_nama             = h.kota_nama,
        tanggal               = detection.tanggal,
        final_alert_level     = final_alert,
        intervention_priority = priority,
        rekomendasi           = rekomendasi,
        reasoning_trace       = ["[Rule-based fallback — LLM tidak tersedia]"],
        tools_called          = [],
        confidence            = "medium",
        is_llm_generated      = False,
    )


# ── ReAct Agent ───────────────────────────────────────────────────────────────

class ReasoningAgent:
    """
    LLM Reasoning Agent menggunakan OpenAI function calling (ReAct pattern).

    Usage:
        context = ToolContext(df)
        agent   = ReasoningAgent(api_key="sk-...", tool_context=context)
        result  = agent.decide(detection_result)
    """

    MAX_ITERATIONS = 3    # maksimum tool call rounds sebelum force-stop
    MODEL          = "google/gemini-2.5-flash"   # default: OpenRouter Gemini Flash

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        tool_context: ToolContext | None = None,
        model: str | None = None,
        fallback_api_key: str | None = None,
        fallback_base_url: str | None = None,
        fallback_model: str | None = None,
    ):
        """
        Args:
            api_key      : LLM API key. Via env: LLM_API_KEY
                           (OpenRouter atau OpenAI langsung)
            base_url     : API base URL. Via env: LLM_BASE_URL
                           OpenRouter : https://openrouter.ai/api/v1
                           OpenAI     : https://api.openai.com/v1
            tool_context : ToolContext dengan DataFrame
            model        : Model ID. Via env: LLM_MODEL (default: google/gemini-2.5-flash)
            fallback_api_key  : Groq API key. Via env: LLM_FALLBACK_API_KEY
            fallback_base_url : Groq base URL. Via env: LLM_FALLBACK_BASE_URL
            fallback_model    : Groq model ID. Via env: LLM_FALLBACK_MODEL
        """
        self._api_key  = api_key  or os.environ.get("LLM_API_KEY",  "")
        self._base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        self._model    = model    or os.environ.get("LLM_MODEL",    self.MODEL)
        self._tool_context = tool_context
        self._client = None
        self._fallback_client = None
        self._fallback_model  = (
            fallback_model
            or os.environ.get("LLM_FALLBACK_MODEL", "llama-3.3-70b-versatile")
        )

        try:
            from openai import OpenAI
            if self._api_key:
                self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)

            _fb_key = (
                fallback_api_key
                or os.environ.get("LLM_FALLBACK_API_KEY", "")
            )
            _fb_url = (
                fallback_base_url
                or os.environ.get("LLM_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
            )
            if _fb_key:
                self._fallback_client = OpenAI(api_key=_fb_key, base_url=_fb_url)
        except ImportError:
            logger.warning("openai package tidak terinstall. Akan menggunakan fallback.")

    def _build_user_message(self, detection: DetectionResult) -> str:
        """Format sinyal deteksi sebagai user message untuk LLM."""
        h  = detection.het_alert
        cp = detection.changepoint
        d  = detection.disparity

        data = {
            "komoditas": h.komoditas_nama,
            "kota": h.kota_nama,
            "tanggal": str(detection.tanggal),
            "harga_aktual": float(h.harga_aktual) if h.harga_aktual is not None else None,
            "het_harga": float(h.het_harga) if h.het_harga is not None else None,
            "has_het": bool(h.has_het),
            "alert_level_aktual": h.alert_level,
            "jarak_ke_het_pct": round(float(h.jarak_ke_het_pct), 1) if h.jarak_ke_het_pct is not None else None,
            "prediksi_p50_7hari": float(h.pred_p50) if h.pred_p50 is not None else None,
            "prediksi_p90_7hari": float(h.pred_p90) if h.pred_p90 is not None else None,
            "pred_alert_level": h.pred_alert_level,
            "is_changepoint": bool(cp.is_changepoint) if cp else False,
            "changepoint_direction": cp.direction if cp else "unknown",
            "changepoint_sigma": round(float(cp.sigma_shift), 2) if cp else 0,
            "is_cusum_alarm": bool(detection.cusum.is_alarm) if detection.cusum else False,
            "cusum_direction": detection.cusum.direction if detection.cusum else "stable",
            "cusum_pos": round(float(detection.cusum.cusum_pos), 2) if detection.cusum else 0,
            "disparity_score": round(float(d.disparity_score), 3) if d and d.disparity_score is not None else None,
            "kota_termahal": d.kota_termahal if d else None,
        }

        return (
            "Berikut data sinyal deteksi untuk dianalisis:\n\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
            + "\n\nGunakan tool untuk menambah context, lalu berikan keputusan akhir dalam format JSON."
        )

    def _decide_with_client(
        self,
        client: Any,
        model: str,
        detection: DetectionResult,
    ) -> DecisionResult:
        """
        Jalankan ReAct loop dengan client dan model yang diberikan.
        Raises exception jika API call gagal (agar caller bisa coba fallback).
        """
        # Set target city's island so compare_regional_prices can prioritise nearby surplus
        kota = detection.het_alert.kota_nama
        df   = self._tool_context.df
        if kota and "provinsi_nama" in df.columns:
            match = df[df["kota_nama"] == kota]
            if not match.empty:
                self._tool_context._target_pulau = self._tool_context._get_pulau(
                    str(match["provinsi_nama"].iloc[0])
                )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": self._build_user_message(detection)},
        ]

        reasoning_trace = []
        tools_called    = []
        final_json      = None

        for _iteration in range(self.MAX_ITERATIONS):
            # Let exceptions propagate so decide() can try the fallback client
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1024,
                timeout=30,  # 30s per LLM call, prevents server hang
            )

            msg = response.choices[0].message

            # No tool call → LLM gave final answer
            if not msg.tool_calls:
                content = msg.content or ""
                reasoning_trace.append(f"[Final] {content[:200]}")

                # Extract JSON from response
                try:
                    import re as _re
                    # 1. Prefer fenced code block: ```json ... ``` or ``` ... ```
                    _fence = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, _re.DOTALL)
                    if _fence:
                        _raw = _fence.group(1)
                    else:
                        # 2. Fall back to first { … last }
                        start = content.find("{")
                        end   = content.rfind("}") + 1
                        _raw  = content[start:end] if start >= 0 and end > start else ""
                    if _raw:
                        # Replace literal (unescaped) newlines inside JSON string values
                        _raw = _re.sub(r'(?<=\S)\n(?=\S)', ' ', _raw)
                        final_json = json.loads(_raw)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Could not parse LLM JSON output, using fallback")

                break

            # Has tool calls — execute them
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]})

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tools_called.append(tool_name)
                reasoning_trace.append(f"[Tool] {tool_name}({tc.function.arguments[:100]})")

                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_result = self._tool_context.call(tool_name, args)
                reasoning_trace.append(f"[Result] {tool_result[:200]}")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      tool_result,
                })

        # Parse final_json into DecisionResult
        h = detection.het_alert
        if final_json:
            return DecisionResult(
                komoditas_nama        = h.komoditas_nama,
                kota_nama             = h.kota_nama,
                tanggal               = detection.tanggal,
                final_alert_level     = final_json.get("final_alert_level", detection.final_alert_level),
                intervention_priority = int(final_json.get("intervention_priority", 3)),
                rekomendasi           = final_json.get("rekomendasi", ""),
                reasoning_trace       = reasoning_trace,
                tools_called          = tools_called,
                confidence            = final_json.get("confidence", "medium"),
                is_llm_generated      = True,
            )
        else:
            # LLM ran but JSON parse failed → rule-based fallback
            result = _rule_based_decision(
                detection,
                self._tool_context.df,
            )
            result.reasoning_trace = reasoning_trace
            result.tools_called    = tools_called
            return result

    def decide(self, detection: DetectionResult) -> DecisionResult:
        """
        Jalankan ReAct loop dan return DecisionResult.

        Urutan fallback:
          1. Primary LLM (LLM_API_KEY / LLM_BASE_URL)
          2. Groq fallback (LLM_FALLBACK_API_KEY)
          3. Rule-based fallback (deterministik, tanpa LLM)
        """
        if self._tool_context is None:
            logger.warning("Tool context tidak tersedia → menggunakan rule-based fallback")
            return _rule_based_decision(detection, pd.DataFrame())

        # Try primary LLM
        if self._client is not None:
            try:
                return self._decide_with_client(self._client, self._model, detection)
            except Exception as e:
                logger.warning(f"Primary LLM gagal ({e}). Mencoba Groq fallback...")

        # Try Groq fallback
        if self._fallback_client is not None:
            try:
                logger.info(f"Menggunakan Groq fallback model: {self._fallback_model}")
                return self._decide_with_client(
                    self._fallback_client, self._fallback_model, detection
                )
            except Exception as e:
                logger.error(f"Groq fallback juga gagal ({e}). Menggunakan rule-based fallback.")

        # Final: rule-based fallback
        logger.warning("Semua LLM tidak tersedia → menggunakan rule-based fallback")
        return _rule_based_decision(
            detection,
            self._tool_context.df,
        )

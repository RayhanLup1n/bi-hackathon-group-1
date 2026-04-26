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
- Pertimbangkan konteks musiman (Ramadan, tahun baru, musim panen)
- Rekomendasi harus spesifik: sebutkan instrumen intervensi \
  (operasi pasar, koordinasi stok antardaerah, sidak harga, usulan peningkatan pasokan)
- Jika ada wilayah surplus teridentifikasi → rekomendasikan koordinasi stok ke wilayah defisit
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
                "Berguna untuk identifikasi wilayah surplus (harga rendah) dan defisit (harga tinggi)."
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

    def __init__(self, df: pd.DataFrame):
        """
        Args:
            df: Full feature DataFrame (dari build_feature_dataset) dengan kolom
                tanggal, komoditas_nama, kota_nama, harga_aktual, het_harga, has_het, bulan
        """
        self.df = df

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

    def compare_regional_prices(self, komoditas_nama: str, tanggal: str) -> dict[str, Any]:
        """Perbandingan harga per kota untuk komoditas pada tanggal tertentu."""
        ts   = pd.Timestamp(tanggal)
        mask = (
            (self.df["komoditas_nama"] == komoditas_nama) &
            (pd.to_datetime(self.df["tanggal"]) == ts)
        )
        sub  = self.df[mask][["kota_nama", "harga_aktual", "harga_ratio_nasional"]].dropna(
            subset=["harga_aktual"]
        )

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
            sub  = latest[["kota_nama", "harga_aktual", "harga_ratio_nasional"]].dropna(
                subset=["harga_aktual"]
            )

        nasional_mean = float(sub["harga_aktual"].mean())
        rows = sub.sort_values("harga_aktual", ascending=False)

        kota_list = []
        for _, r in rows.iterrows():
            kota_list.append({
                "kota": r["kota_nama"],
                "harga": int(r["harga_aktual"]),
                "ratio_vs_nasional": round(float(r.get("harga_ratio_nasional") or
                                                  r["harga_aktual"] / nasional_mean), 3),
                "status": "surplus (harga rendah)" if r["harga_aktual"] < nasional_mean * 0.95
                          else "defisit (harga tinggi)" if r["harga_aktual"] > nasional_mean * 1.05
                          else "normal",
            })

        return {
            "komoditas_nama": komoditas_nama,
            "tanggal": tanggal,
            "rata_rata_nasional": int(nasional_mean),
            "kota_termahal": kota_list[0] if kota_list else None,
            "kota_termurah": kota_list[-1] if kota_list else None,
            "semua_kota": kota_list,
        }

    def get_upcoming_events(self, tanggal_referensi: str) -> dict[str, Any]:
        """Event musiman dalam 30 hari ke depan dan dampak harga historisnya."""
        ref  = date.fromisoformat(tanggal_referensi)
        events = []

        # Ramadan/Lebaran proxy: bulan 3-5 (lihat is_ramadan_season)
        for offset in range(1, 31):
            d = ref + timedelta(days=offset)
            if d.month in (3, 4, 5):
                events.append({
                    "event": "Musim Ramadan/Lebaran",
                    "tanggal_mulai": str(date(d.year, 3, 1)),
                    "hari_ke_depan": (date(d.year, 3, 1) - ref).days,
                    "dampak_harga_historis": "+15–30% untuk cabai, bawang, daging, telur",
                    "catatan": "Proxy bulan 3-5; cek kalender Hijriah untuk akurasi",
                })
                break

        # Tahun baru / akhir tahun
        for offset in range(1, 31):
            d = ref + timedelta(days=offset)
            if d.month == 12 and d.day >= 20:
                events.append({
                    "event": "Libur Natal & Tahun Baru",
                    "tanggal": str(d),
                    "hari_ke_depan": offset,
                    "dampak_harga_historis": "+5–15% untuk daging, telur, sayuran",
                })
                break

        if not events:
            events.append({
                "event": "Tidak ada event besar dalam 30 hari ke depan",
                "hari_ke_depan": None,
                "dampak_harga_historis": "Normal seasonality",
            })

        return {
            "tanggal_referensi": tanggal_referensi,
            "window_hari": 30,
            "events": events,
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
            f"Disparitas harga antarkota signifikan — {disp.kota_termurah} terindikasi surplus, "
            f"koordinasi stok ke {disp.kota_termahal} direkomendasikan."
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

    MAX_ITERATIONS = 6    # maksimum tool call rounds sebelum force-stop
    MODEL          = "gpt-4o-mini"

    def __init__(
        self,
        api_key: str | None = None,
        tool_context: ToolContext | None = None,
        model: str | None = None,
    ):
        """
        Args:
            api_key      : OpenAI API key (atau via env OPENAI_API_KEY)
            tool_context : ToolContext dengan DataFrame
            model        : Override model (default: gpt-4o-mini)
        """
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._tool_context = tool_context
        self._model = model or self.MODEL
        self._client = None

        if self._api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
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
            "harga_aktual": h.harga_aktual,
            "het_harga": h.het_harga,
            "has_het": h.has_het,
            "alert_level_aktual": h.alert_level,
            "jarak_ke_het_pct": round(h.jarak_ke_het_pct, 1) if h.jarak_ke_het_pct else None,
            "prediksi_p50_7hari": h.pred_p50,
            "prediksi_p90_7hari": h.pred_p90,
            "pred_alert_level": h.pred_alert_level,
            "is_changepoint": cp.is_changepoint if cp else False,
            "changepoint_direction": cp.direction if cp else "unknown",
            "changepoint_sigma": round(cp.sigma_shift, 2) if cp else 0,
            "disparity_score": round(d.disparity_score, 3) if d else None,
            "kota_termahal": d.kota_termahal if d else None,
            "kota_termurah": d.kota_termurah if d else None,
        }

        return (
            "Berikut data sinyal deteksi untuk dianalisis:\n\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
            + "\n\nGunakan tool untuk menambah context, lalu berikan keputusan akhir dalam format JSON."
        )

    def decide(self, detection: DetectionResult) -> DecisionResult:
        """
        Jalankan ReAct loop dan return DecisionResult.

        Jika LLM client tidak tersedia → gunakan rule-based fallback.
        """
        if self._client is None or self._tool_context is None:
            logger.warning("LLM client/context tidak tersedia → menggunakan rule-based fallback")
            return _rule_based_decision(
                detection,
                self._tool_context.df if self._tool_context else pd.DataFrame(),
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": self._build_user_message(detection)},
        ]

        reasoning_trace = []
        tools_called    = []
        final_json      = None

        for iteration in range(self.MAX_ITERATIONS):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=1024,
                )
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
                return _rule_based_decision(
                    detection,
                    self._tool_context.df if self._tool_context else pd.DataFrame(),
                )

            msg = response.choices[0].message

            # No tool call → LLM gave final answer
            if not msg.tool_calls:
                content = msg.content or ""
                reasoning_trace.append(f"[Final] {content[:200]}")

                # Extract JSON from response
                try:
                    # Try to find JSON block in the response
                    start = content.find("{")
                    end   = content.rfind("}") + 1
                    if start >= 0 and end > start:
                        final_json = json.loads(content[start:end])
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
            # LLM ran but JSON parse failed → fallback
            result = _rule_based_decision(
                detection,
                self._tool_context.df if self._tool_context else pd.DataFrame(),
            )
            result.reasoning_trace = reasoning_trace
            result.tools_called    = tools_called
            return result

"""
pipeline.py — Orchestrator: 3-Layer ML Pipeline RADAR Pangan
=============================================================

Menggabungkan Lapis 1 (Forecast), Lapis 2 (Detection), Lapis 3 (Decision).

Usage:
    pipeline = RadarPipeline.from_config(
        models_dir="ml/models",
        het_csv="ml/data/het_reference.csv",
        duckdb_path="/opt/airflow/data/pihps.duckdb",  # atau None jika pakai parquet
        parquet_path="ml/data/export_modelling.parquet",
        openai_api_key="sk-...",
    )
    pipeline.load()

    # Analisis tunggal
    result = pipeline.analyze("Cabai Merah Keriting", "Bandung", date(2026, 4, 26))

    # Batch analisis semua komoditas-kota pada tanggal tertentu
    results = pipeline.analyze_all(date(2026, 4, 26))

    # Dapatkan semua alert aktif, diurutkan prioritas
    alerts = pipeline.get_active_alerts(date(2026, 4, 26))
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from ml.src.decide import DecisionResult, ReasoningAgent, ToolContext
from ml.src.detect import AlertLevel, DetectionResult, run_detection
from ml.src.features import (
    add_het_features,
    add_targets,
    build_feature_dataset,
    encode_categoricals,
    get_feature_cols,
    load_from_postgres,
)
from ml.src.train import load_model


# ── Full Analysis Result ──────────────────────────────────────────────────────

@dataclass
class FullAnalysisResult:
    """Gabungan output semua 3 lapis untuk satu (komoditas, kota, tanggal)."""
    komoditas_nama:  str
    kota_nama:       str
    tanggal:         date

    # Lapis 1 — Prediksi
    pred_p50_7d:     float | None = None
    pred_p90_7d:     float | None = None
    pred_p50_14d:    float | None = None
    pred_p90_14d:    float | None = None

    # Lapis 2 — Detection
    detection:       DetectionResult | None = None

    # Lapis 3 — Decision
    decision:        DecisionResult | None = None

    @property
    def final_alert_level(self) -> AlertLevel:
        if self.decision:
            return self.decision.final_alert_level
        if self.detection:
            return self.detection.final_alert_level
        return "unknown"

    @property
    def priority(self) -> int:
        return self.decision.intervention_priority if self.decision else 5

    def to_dict(self) -> dict[str, Any]:
        """Serializable dict untuk API response."""
        return {
            "komoditas_nama":   self.komoditas_nama,
            "kota_nama":        self.kota_nama,
            "tanggal":          str(self.tanggal),
            "predictions": {
                "p50_7d":  self.pred_p50_7d,
                "p90_7d":  self.pred_p90_7d,
                "p50_14d": self.pred_p50_14d,
                "p90_14d": self.pred_p90_14d,
            },
            "detection": {
                "alert_level":       self.detection.het_alert.alert_level if self.detection else None,
                "pred_alert_level":  self.detection.het_alert.pred_alert_level if self.detection else None,
                "is_changepoint":    bool(self.detection.changepoint.is_changepoint)
                                     if self.detection and self.detection.changepoint else False,
                "is_cusum_alarm":    bool(self.detection.cusum.is_alarm)
                                     if self.detection and self.detection.cusum else False,
                "cusum_direction":   self.detection.cusum.direction
                                     if self.detection and self.detection.cusum else "stable",
                "disparity_score":   float(self.detection.disparity.disparity_score)
                                     if self.detection and self.detection.disparity and self.detection.disparity.disparity_score is not None else None,
                "jarak_ke_het_pct":  float(self.detection.het_alert.jarak_ke_het_pct)
                                     if self.detection and self.detection.het_alert.jarak_ke_het_pct is not None else None,
                "het_harga":         float(self.detection.het_alert.het_harga)
                                     if self.detection and self.detection.het_alert.het_harga is not None else None,
            } if self.detection else {},
            "decision": {
                "final_alert_level":     self.decision.final_alert_level,
                "intervention_priority": self.decision.intervention_priority,
                "rekomendasi":           self.decision.rekomendasi,
                "confidence":            self.decision.confidence,
                "is_llm_generated":      bool(self.decision.is_llm_generated),
                "reasoning_trace":       self.decision.reasoning_trace,
            } if self.decision else {},
        }


# ── Pipeline ──────────────────────────────────────────────────────────────────

class RadarPipeline:
    """
    Orchestrates all 3 ML layers.

    Lifecycle:
        1. __init__ / from_config — set paths and config
        2. load()                 — load data + models into memory
        3. analyze() / analyze_all() / get_active_alerts()
    """

    def __init__(
        self,
        models_dir: str | Path,
        het_csv: str | Path,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        llm_model: str | None = None,
        llm_fallback_api_key: str | None = None,
        llm_fallback_base_url: str | None = None,
        llm_fallback_model: str | None = None,
    ):
        self.models_dir   = Path(models_dir)
        self.het_csv      = Path(het_csv)
        self.llm_api_key  = llm_api_key  or os.environ.get("LLM_API_KEY",  "")
        self.llm_base_url = llm_base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_model    = llm_model    or os.environ.get("LLM_MODEL",    "google/gemini-2.5-flash")
        self.llm_fallback_api_key  = llm_fallback_api_key  or os.environ.get("LLM_FALLBACK_API_KEY",  "")
        self.llm_fallback_base_url = llm_fallback_base_url or os.environ.get("LLM_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
        self.llm_fallback_model    = llm_fallback_model    or os.environ.get("LLM_FALLBACK_MODEL",    "llama-3.3-70b-versatile")

        # Loaded on .load()
        self._df: pd.DataFrame | None = None
        self._models: dict[str, Any]  = {}      # model_name → (model, feature_cols)
        self._agent: ReasoningAgent | None = None
        self._loaded = False

    @classmethod
    def from_config(
        cls,
        models_dir: str = "ml/models",
        het_csv: str = "ml/data/het_reference.csv",
        pg_conn_string: str | None = None,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        llm_model: str | None = None,
        llm_fallback_api_key: str | None = None,
        llm_fallback_base_url: str | None = None,
        llm_fallback_model: str | None = None,
    ) -> "RadarPipeline":
        """Factory method: create pipeline dan langsung load data dari Supabase."""
        pipeline = cls(
            models_dir=models_dir,
            het_csv=het_csv,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_fallback_api_key=llm_fallback_api_key,
            llm_fallback_base_url=llm_fallback_base_url,
            llm_fallback_model=llm_fallback_model,
        )
        pipeline.load(pg_conn_string=pg_conn_string)
        return pipeline

    def load(
        self,
        pg_conn_string: str | None = None,
    ) -> None:
        """
        Load data dari Supabase/PostgreSQL dan semua model ke memory.
        Hanya perlu dipanggil sekali (di startup server).
        """
        logger.info("Loading RadarPipeline...")

        # 1. Load data
        if pg_conn_string:
            raw_df = load_from_postgres(pg_conn_string)
        else:
            logger.warning(
                "Tidak ada sumber data tersedia. "
                "Pipeline akan berjalan tanpa historical context (reduce functionality)."
            )
            raw_df = pd.DataFrame()

        if not raw_df.empty:
            logger.info("Building feature dataset...")
            self._df = add_het_features(raw_df, self.het_csv)
            self._df = add_targets(self._df, horizons=[7, 14])
            self._df = encode_categoricals(self._df)
            self._df["tanggal"] = pd.to_datetime(self._df["tanggal"])
        else:
            self._df = pd.DataFrame()

        # 2. Load models
        self._models = {}
        for model_file in self.models_dir.glob("lgbm_*.pkl"):
            name = model_file.stem
            model, feature_cols = load_model(model_file)
            self._models[name] = (model, feature_cols)
            logger.info(f"Loaded model: {name}")

        if not self._models:
            logger.warning(f"Tidak ada model ditemukan di {self.models_dir}. Jalankan train.py dulu.")

        # 3. Init agent
        tool_context = ToolContext(self._df) if not self._df.empty else None
        self._agent  = ReasoningAgent(
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
            model=self.llm_model,
            tool_context=tool_context,
            fallback_api_key=self.llm_fallback_api_key,
            fallback_base_url=self.llm_fallback_base_url,
            fallback_model=self.llm_fallback_model,
        )

        self._loaded = True
        logger.info(
            f"Pipeline loaded: {len(self._models)} models | "
            f"{len(self._df):,} rows data | "
            f"LLM={'on' if self._agent._client else ('groq-fallback' if self._agent._fallback_client else 'rule-based')}"
        )

    def _get_row(self, komoditas_nama: str, kota_nama: str, tanggal: date) -> pd.Series | None:
        """Ambil satu baris data dari DataFrame."""
        if self._df is None or self._df.empty:
            return None

        t_pd = pd.Timestamp(tanggal)
        mask = (
            (self._df["komoditas_nama"] == komoditas_nama) &
            (self._df["kota_nama"] == kota_nama) &
            (self._df["tanggal"] == t_pd)
        )
        sub = self._df[mask]
        if sub.empty:
            # Try nearest available date (within 7 days back)
            for delta in range(1, 8):
                mask_back = (
                    (self._df["komoditas_nama"] == komoditas_nama) &
                    (self._df["kota_nama"] == kota_nama) &
                    (self._df["tanggal"] == t_pd - pd.Timedelta(days=delta))
                )
                sub = self._df[mask_back]
                if not sub.empty:
                    logger.debug(f"Using data from {delta} days ago for ({komoditas_nama}, {kota_nama})")
                    break

        return sub.iloc[0] if not sub.empty else None

    def _predict(self, row: pd.Series, horizon: int) -> tuple[float | None, float | None]:
        """
        Run Lapis 1 predictions for one row.

        Returns:
            (pred_p50, pred_p90) or (None, None) if models not available
        """
        m50_key = f"lgbm_q50_t{horizon}"
        m90_key = f"lgbm_q90_t{horizon}"

        if m50_key not in self._models or m90_key not in self._models:
            return None, None

        model50, fcols50 = self._models[m50_key]
        model90, fcols90 = self._models[m90_key]

        # Build feature vector
        available_cols50 = [c for c in fcols50 if c in row.index]
        available_cols90 = [c for c in fcols90 if c in row.index]

        if not available_cols50:
            return None, None

        x50 = row[available_cols50].values.reshape(1, -1)
        x90 = row[available_cols90].values.reshape(1, -1) if available_cols90 else x50

        try:
            p50 = float(model50.predict(x50)[0])
            p90 = float(model90.predict(x90)[0])
            return p50, p90
        except Exception as e:
            logger.warning(f"Prediction error: {e}")
            return None, None

    def analyze(
        self,
        komoditas_nama: str,
        kota_nama: str,
        tanggal: date,
    ) -> FullAnalysisResult:
        """
        Jalankan full 3-layer analysis untuk satu (komoditas, kota, tanggal).

        Returns:
            FullAnalysisResult dengan prediksi, detection, dan decision.
        """
        if not self._loaded:
            raise RuntimeError("Pipeline belum di-load. Panggil pipeline.load() dulu.")

        result = FullAnalysisResult(
            komoditas_nama=komoditas_nama,
            kota_nama=kota_nama,
            tanggal=tanggal,
        )

        row = self._get_row(komoditas_nama, kota_nama, tanggal)
        if row is None:
            logger.warning(f"Data tidak ditemukan: ({komoditas_nama}, {kota_nama}, {tanggal})")
            return result

        # ── Lapis 1: Prediksi ─────────────────────────────────────────────────
        result.pred_p50_7d,  result.pred_p90_7d  = self._predict(row, horizon=7)
        result.pred_p50_14d, result.pred_p90_14d = self._predict(row, horizon=14)

        # ── Lapis 2: Detection ────────────────────────────────────────────────
        if not self._df.empty:
            history_df = self._df[
                (self._df["comcat_id"] == row["comcat_id"]) &
                (self._df["kota_nama"] == kota_nama) &
                (self._df["tanggal"] <= pd.Timestamp(tanggal))
            ].copy()

            day_df = self._df[
                (self._df["komoditas_nama"] == komoditas_nama) &
                (self._df["tanggal"] == pd.Timestamp(tanggal))
            ].copy()

            result.detection = run_detection(
                row=row,
                history_df=history_df,
                day_df=day_df,
                pred_p50=result.pred_p50_7d,
                pred_p90=result.pred_p90_7d,
            )

        # ── Lapis 3: Decision (LLM Reasoning Agent) ───────────────────────────
        if result.detection and self._agent:
            result.decision = self._agent.decide(result.detection)

        return result

    def analyze_all(
        self,
        tanggal: date,
        komoditas_filter: list[str] | None = None,
        kota_filter: list[str] | None = None,
    ) -> list[FullAnalysisResult]:
        """
        Analisis semua kombinasi (komoditas, kota) pada satu tanggal.

        Args:
            tanggal          : Tanggal analisis
            komoditas_filter : Jika diisi, hanya analisis komoditas ini
            kota_filter      : Jika diisi, hanya analisis kota ini

        Returns:
            List of FullAnalysisResult, sorted by priority (ascending)
        """
        if self._df is None or self._df.empty:
            logger.warning("DataFrame kosong, tidak ada data untuk dianalisis")
            return []

        t_pd  = pd.Timestamp(tanggal)
        df_day = self._df[self._df["tanggal"] == t_pd]

        if df_day.empty:
            # Fallback to latest available date
            latest = self._df["tanggal"].max()
            logger.warning(f"Data tanggal {tanggal} tidak ada, pakai tanggal terakhir: {latest.date()}")
            df_day  = self._df[self._df["tanggal"] == latest]
            tanggal = latest.date()

        if komoditas_filter:
            df_day = df_day[df_day["komoditas_nama"].isin(komoditas_filter)]
        if kota_filter:
            df_day = df_day[df_day["kota_nama"].isin(kota_filter)]

        combos = df_day[["komoditas_nama", "kota_nama"]].drop_duplicates()
        results = []

        logger.info(f"Analyzing {len(combos)} (komoditas, kota) pairs for {tanggal}...")

        for _, combo in combos.iterrows():
            result = self.analyze(combo["komoditas_nama"], combo["kota_nama"], tanggal)
            results.append(result)

        results.sort(key=lambda r: r.priority)
        logger.info(f"Analysis complete: {len(results)} results")
        return results

    def get_active_alerts(
        self,
        tanggal: date,
        min_alert_level: AlertLevel = "yellow",
    ) -> list[FullAnalysisResult]:
        """
        Dapatkan semua alert aktif pada tanggal tertentu.
        Diurutkan: priority asc, alert_level desc (red first).

        Args:
            tanggal          : Tanggal analisis
            min_alert_level  : Minimum level untuk masuk daftar alert (default: "yellow")
        """
        _rank = {"green": 0, "yellow": 1, "red": 2, "unknown": -1}
        min_rank = _rank.get(min_alert_level, 0)

        all_results = self.analyze_all(tanggal)
        alerts = [
            r for r in all_results
            if _rank.get(r.final_alert_level, -1) >= min_rank
        ]

        alerts.sort(
            key=lambda r: (-_rank.get(r.final_alert_level, 0), r.priority)
        )

        logger.info(
            f"Active alerts ({min_alert_level}+): {len(alerts)} / {len(all_results)} combinations"
        )
        return alerts

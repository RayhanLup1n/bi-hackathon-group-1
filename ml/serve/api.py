"""
serve/api.py — FastAPI Inference Server untuk ML Layer RADAR Pangan
====================================================================

Endpoints:
  GET  /health                  — Health check + status pipeline
  POST /api/v1/analyze          — Analisis tunggal (komoditas, kota, tanggal)
  POST /api/v1/batch            — Batch analisis multiple (komoditas, kota)
  GET  /api/v1/alerts           — Semua alert aktif pada tanggal tertentu
  GET  /api/v1/komoditas        — Daftar komoditas yang tersedia
  GET  /api/v1/kota             — Daftar kota yang tersedia

Startup:
  Pipeline di-load sekali pada startup (lifespan context manager).
  Model pkl dan data diload ke memory → latency inferensi <100ms per request.

Run:
  uvicorn ml.serve.api:app --host 0.0.0.0 --port 8001 --reload
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

from ml.src.pipeline import FullAnalysisResult, RadarPipeline

# ── Config dari environment ───────────────────────────────────────────────────

MODELS_DIR     = os.environ.get("ML_MODELS_DIR",    "ml/models")
HET_CSV        = os.environ.get("ML_HET_CSV",       "ml/data/het_reference.csv")
DUCKDB_PATH    = os.environ.get("DUCKDB_PATH",      "")
PARQUET_PATH   = os.environ.get("ML_PARQUET_PATH",  "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY",   "")

# ── Global pipeline instance ──────────────────────────────────────────────────

_pipeline: RadarPipeline | None = None


# ── Lifespan: load pipeline on startup ───────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    logger.info("Starting ML inference server...")

    _pipeline = RadarPipeline(
        models_dir=MODELS_DIR,
        het_csv=HET_CSV,
        openai_api_key=OPENAI_API_KEY,
    )
    _pipeline.load(
        duckdb_path=DUCKDB_PATH or None,
        parquet_path=PARQUET_PATH or None,
    )

    logger.info("ML pipeline ready.")
    yield

    logger.info("Shutting down ML inference server.")
    _pipeline = None


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RADAR Pangan — ML Inference API",
    description=(
        "3-layer ML inference: "
        "Lapis 1 (LightGBM Quantile Forecast) + "
        "Lapis 2 (Bayesian CP + HET Detection) + "
        "Lapis 3 (LLM Reasoning Agent)"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    komoditas_nama: str = Field(..., example="Cabai Merah Keriting")
    kota_nama:      str = Field(..., example="Bandung")
    tanggal:        date = Field(default_factory=date.today)


class BatchAnalyzeRequest(BaseModel):
    requests:  list[AnalyzeRequest]
    tanggal:   date | None = None   # override tanggal di semua requests jika diisi


class AlertsQuery(BaseModel):
    tanggal:         date = Field(default_factory=date.today)
    min_alert_level: str  = Field(default="yellow", pattern="^(yellow|red)$")


def _serialize_result(result: FullAnalysisResult) -> dict[str, Any]:
    """Convert FullAnalysisResult ke JSON-serializable dict."""
    return result.to_dict()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_pipeline() -> RadarPipeline:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline belum siap. Coba lagi sebentar.")
    return _pipeline


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"])
def health_check():
    """Health check — cek apakah pipeline sudah loaded."""
    if _pipeline is None:
        return {"status": "loading", "models_loaded": 0}

    return {
        "status": "ok",
        "models_loaded":  len(_pipeline._models),
        "has_data":       _pipeline._df is not None and not _pipeline._df.empty,
        "llm_available":  _pipeline._agent is not None and _pipeline._agent._client is not None,
        "data_rows":      len(_pipeline._df) if _pipeline._df is not None else 0,
    }


@app.post("/api/v1/analyze", tags=["inference"])
def analyze_single(req: AnalyzeRequest) -> dict[str, Any]:
    """
    Analisis tunggal untuk satu (komoditas, kota, tanggal).

    Menjalankan full 3-layer pipeline:
    - Lapis 1: Prediksi harga 7 & 14 hari ke depan (Q50/Q90)
    - Lapis 2: Deteksi changepoint + HET alert
    - Lapis 3: LLM reasoning → rekomendasi intervensi
    """
    pipeline = _require_pipeline()

    result = pipeline.analyze(
        komoditas_nama=req.komoditas_nama,
        kota_nama=req.kota_nama,
        tanggal=req.tanggal,
    )

    return _serialize_result(result)


@app.post("/api/v1/batch", tags=["inference"])
def analyze_batch(req: BatchAnalyzeRequest) -> list[dict[str, Any]]:
    """
    Batch analisis untuk multiple (komoditas, kota).

    Jika req.tanggal diisi, semua request menggunakan tanggal tersebut.
    """
    pipeline = _require_pipeline()
    results  = []

    for single in req.requests:
        tanggal = req.tanggal or single.tanggal
        result  = pipeline.analyze(
            komoditas_nama=single.komoditas_nama,
            kota_nama=single.kota_nama,
            tanggal=tanggal,
        )
        results.append(_serialize_result(result))

    return results


@app.get("/api/v1/alerts", tags=["monitoring"])
def get_active_alerts(
    tanggal:         date = Query(default_factory=date.today),
    min_alert_level: str  = Query(default="yellow", pattern="^(yellow|red)$"),
) -> dict[str, Any]:
    """
    Semua alert aktif pada tanggal tertentu, diurutkan priority (paling urgent duluan).

    Berguna untuk:
    - Dashboard TPID: tampilkan tabel prioritas intervensi
    - Notifikasi otomatis: trigger alert ke channel Telegram/email
    """
    pipeline = _require_pipeline()

    from ml.src.detect import AlertLevel
    alerts = pipeline.get_active_alerts(
        tanggal=tanggal,
        min_alert_level=min_alert_level,  # type: ignore[arg-type]
    )

    return {
        "tanggal":          str(tanggal),
        "min_alert_level":  min_alert_level,
        "total_alerts":     len(alerts),
        "alerts":           [_serialize_result(a) for a in alerts],
    }


@app.get("/api/v1/komoditas", tags=["reference"])
def list_komoditas() -> dict[str, Any]:
    """Daftar komoditas yang tersedia dalam dataset."""
    pipeline = _require_pipeline()

    if pipeline._df is None or pipeline._df.empty:
        return {"komoditas": []}

    names = sorted(pipeline._df["komoditas_nama"].dropna().unique().tolist())
    return {"total": len(names), "komoditas": names}


@app.get("/api/v1/kota", tags=["reference"])
def list_kota() -> dict[str, Any]:
    """Daftar kota yang tersedia dalam dataset."""
    pipeline = _require_pipeline()

    if pipeline._df is None or pipeline._df.empty:
        return {"kota": []}

    kota_df = (
        pipeline._df[["kota_nama", "provinsi_nama"]]
        .drop_duplicates()
        .sort_values("kota_nama")
    )
    return {
        "total": len(kota_df),
        "kota": kota_df.to_dict(orient="records"),
    }


@app.get("/api/v1/summary/{tanggal}", tags=["monitoring"])
def daily_summary(tanggal: date) -> dict[str, Any]:
    """
    Ringkasan harian: berapa red/yellow/green, komoditas paling berisiko.

    Berguna untuk tampilan homepage dashboard.
    """
    pipeline = _require_pipeline()

    all_results = pipeline.analyze_all(tanggal)

    if not all_results:
        return {
            "tanggal":       str(tanggal),
            "total_analyzed": 0,
            "alert_counts":  {"red": 0, "yellow": 0, "green": 0, "unknown": 0},
            "top_priority":  [],
        }

    from collections import Counter
    alert_counts = Counter(r.final_alert_level for r in all_results)

    top5 = sorted(all_results, key=lambda r: r.priority)[:5]

    return {
        "tanggal":         str(tanggal),
        "total_analyzed":  len(all_results),
        "alert_counts":    dict(alert_counts),
        "top_priority": [
            {
                "rank":             i + 1,
                "komoditas":        r.komoditas_nama,
                "kota":             r.kota_nama,
                "alert_level":      r.final_alert_level,
                "rekomendasi":      r.decision.rekomendasi if r.decision else None,
            }
            for i, r in enumerate(top5)
        ],
    }

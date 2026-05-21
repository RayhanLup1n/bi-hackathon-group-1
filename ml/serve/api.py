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

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

from pathlib import Path

from dotenv import load_dotenv

from ml.src.pipeline import FullAnalysisResult, RadarPipeline

# ── Paths relative to this file (repo-root-independent) ──────────────────────
_API_DIR  = Path(__file__).resolve().parent          # ml/serve/
_ML_DIR   = _API_DIR.parent                          # ml/
_REPO_DIR = _ML_DIR.parent                           # repo root

# ── Load .env (ml/.env relative to this file) ─────────────────────────────────
load_dotenv(_ML_DIR / ".env", override=False)

# ── Config dari environment ───────────────────────────────────────────────────

MODELS_DIR    = os.environ.get("ML_MODELS_DIR",    str(_ML_DIR / "models"))
HET_CSV       = os.environ.get("ML_HET_CSV",       str(_ML_DIR / "data" / "het_reference.csv"))
LLM_API_KEY   = os.environ.get("LLM_API_KEY",      "")
LLM_BASE_URL  = os.environ.get("LLM_BASE_URL",     "https://openrouter.ai/api/v1")
LLM_MODEL     = os.environ.get("LLM_MODEL",        "google/gemini-2.5-flash")

# Fallback LLM (Groq) — used when primary LLM fails
LLM_FALLBACK_API_KEY  = os.environ.get("LLM_FALLBACK_API_KEY",  "")
LLM_FALLBACK_BASE_URL = os.environ.get("LLM_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
LLM_FALLBACK_MODEL    = os.environ.get("LLM_FALLBACK_MODEL",    "llama-3.3-70b-versatile")

# Supabase / PostgreSQL
_SUPA_HOST = os.environ.get("SUPABASE_HOST", "")
_SUPA_PORT = os.environ.get("SUPABASE_PORT", "5432")
_SUPA_DB   = os.environ.get("SUPABASE_DB",   "postgres")
_SUPA_USER = os.environ.get("SUPABASE_USER", "")
_SUPA_PASS = os.environ.get("SUPABASE_PASSWORD", "")
PG_CONN_STRING = (
    f"postgresql://{_SUPA_USER}:{_SUPA_PASS}@{_SUPA_HOST}:{_SUPA_PORT}/{_SUPA_DB}"
    if _SUPA_HOST and _SUPA_USER and _SUPA_PASS
    else ""
)

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
        llm_api_key=LLM_API_KEY,
        llm_base_url=LLM_BASE_URL,
        llm_model=LLM_MODEL,
        llm_fallback_api_key=LLM_FALLBACK_API_KEY,
        llm_fallback_base_url=LLM_FALLBACK_BASE_URL,
        llm_fallback_model=LLM_FALLBACK_MODEL,
    )
    _pipeline.load(
        pg_conn_string=PG_CONN_STRING or None,
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


class SimulateScenario(BaseModel):
    harga_intervensi: float | None = Field(None, description="Harga target setelah intervensi (Rp)")
    pct_shock:        float | None = Field(None, description="Persen perubahan harga (negatif = turun, mis. -15 = -15%)")


def _serialize_result(result: FullAnalysisResult) -> dict[str, Any]:
    """Convert FullAnalysisResult ke JSON-serializable dict."""
    return result.to_dict()


def _persist_predictions(result: FullAnalysisResult) -> None:
    """
    Insert predictions from FullAnalysisResult into app.ml_predictions.
    Skips gracefully if predictions are null or DB not available.
    Runs as a fire-and-forget background task.
    """
    if not PG_CONN_STRING:
        return

    # Only insert if we have at least one non-null prediction
    has_pred = any([
        result.pred_p50_7d, result.pred_p90_7d,
        result.pred_p50_14d, result.pred_p90_14d,
    ])
    if not has_pred:
        return

    # Look up comcat_id + kota_id from the in-memory DataFrame
    df = _pipeline._df if _pipeline else None
    if df is None or df.empty:
        return

    sub = df[df["komoditas_nama"] == result.komoditas_nama]
    if sub.empty:
        return
    comcat_id = str(sub["comcat_id"].iloc[0])

    sub_kota = df[df["kota_nama"] == result.kota_nama]
    if sub_kota.empty:
        return
    kota_id = int(sub_kota["kota_id"].iloc[0])

    from datetime import timedelta
    import psycopg2

    rows: list[tuple] = []
    for horizon, p50, p90 in [
        (7,  result.pred_p50_7d,  result.pred_p90_7d),
        (14, result.pred_p50_14d, result.pred_p90_14d),
    ]:
        if p50 is None:
            continue
        target_date = result.tanggal + timedelta(days=horizon)
        rows.append((
            comcat_id,
            kota_id,
            result.tanggal,
            target_date,
            round(p50, 2),
            None,                  # confidence_lower — no P10 model
            round(p90, 2) if p90 else None,
            f"lgbm_q50_t{horizon}+q90_t{horizon}",
        ))

    if not rows:
        return

    try:
        conn = psycopg2.connect(PG_CONN_STRING)
        cur  = conn.cursor()
        for row in rows:
            # Upsert: delete existing then insert
            cur.execute(
                """
                DELETE FROM app.ml_predictions
                WHERE komoditas_id = %s AND kota_id = %s
                  AND prediction_date = %s AND target_date = %s
                """,
                (row[0], row[1], row[2], row[3]),
            )
            cur.execute(
                """
                INSERT INTO app.ml_predictions
                    (komoditas_id, kota_id, prediction_date, target_date,
                     predicted_price, confidence_lower, confidence_upper, model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                row,
            )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(
            f"Saved {len(rows)} predictions for "
            f"({result.komoditas_nama}, {result.kota_nama}, {result.tanggal})"
        )
    except Exception as exc:
        logger.warning(f"Gagal simpan prediksi ke DB: {exc}")


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
def analyze_single(req: AnalyzeRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Analisis tunggal untuk satu (komoditas, kota, tanggal).

    Menjalankan full 3-layer pipeline:
    - Lapis 1: Prediksi harga 7 & 14 hari ke depan (Q50/Q90)
    - Lapis 2: Deteksi changepoint + HET alert
    - Lapis 3: LLM reasoning → rekomendasi intervensi
    """
    import traceback
    pipeline = _require_pipeline()

    try:
        result = pipeline.analyze(
            komoditas_nama=req.komoditas_nama,
            kota_nama=req.kota_nama,
            tanggal=req.tanggal,
        )
    except Exception as exc:
        logger.error(f"analyze() error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(_persist_predictions, result)
    return _serialize_result(result)


@app.post("/api/v1/batch", tags=["inference"])
def analyze_batch(req: BatchAnalyzeRequest, background_tasks: BackgroundTasks) -> list[dict[str, Any]]:
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
        background_tasks.add_task(_persist_predictions, result)

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


class SimulateRequest(BaseModel):
    komoditas_nama: str  = Field(..., example="Bawang Merah Ukuran Sedang")
    kota_nama:      str  = Field(..., example="Kota Bandung")
    tanggal:        date = Field(default_factory=date.today)
    scenario:       SimulateScenario
    with_llm:       bool = Field(False, description="Jalankan LLM reasoning untuk simulasi (lebih lambat)")


@app.post("/api/v1/simulate", tags=["simulation"])
def simulate_intervention(req: SimulateRequest) -> dict[str, Any]:
    """
    Simulasi 'bagaimana jika' harga berubah setelah intervensi.

    Berguna untuk:
    - Evaluasi efektivitas operasi pasar (harga turun ke HET)
    - Simulasi dampak kebijakan (pct_shock = -20% → apakah alert berubah?)

    Kembalikan: baseline vs simulated (Lapis 1 + 2), plus delta ringkasan.
    """
    import pandas as pd
    from ml.src.detect import run_detection
    from ml.src.pipeline import FullAnalysisResult

    pipeline = _require_pipeline()

    # Validate scenario
    if req.scenario.harga_intervensi is None and req.scenario.pct_shock is None:
        raise HTTPException(
            status_code=400,
            detail="Isi salah satu: scenario.harga_intervensi (harga absolut) atau scenario.pct_shock (persen perubahan).",
        )

    # 1. Get feature row
    row = pipeline._get_row(req.komoditas_nama, req.kota_nama, req.tanggal)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Data tidak ditemukan: ({req.komoditas_nama}, {req.kota_nama}, {req.tanggal})",
        )

    original_harga = float(row.get("harga_aktual", 0) or 0)

    # 2. Baseline — Lapis 1 + 2 only (no LLM, fast)
    base_p50_7d,  base_p90_7d  = pipeline._predict(row, horizon=7)
    base_p50_14d, base_p90_14d = pipeline._predict(row, horizon=14)
    base_detection = None
    if pipeline._df is not None and not pipeline._df.empty:
        history_df = pipeline._df[
            (pipeline._df["comcat_id"] == row["comcat_id"]) &
            (pipeline._df["kota_nama"] == req.kota_nama) &
            (pipeline._df["tanggal"] <= pd.Timestamp(req.tanggal))
        ].copy()
        base_day_df = pipeline._df[
            (pipeline._df["komoditas_nama"] == req.komoditas_nama) &
            (pipeline._df["tanggal"] == pd.Timestamp(req.tanggal))
        ].copy()
        base_detection = run_detection(
            row=row,
            history_df=history_df,
            day_df=base_day_df,
            pred_p50=base_p50_7d,
            pred_p90=base_p90_7d,
        )

    # 3. Compute simulated price
    if req.scenario.harga_intervensi is not None:
        sim_harga = float(req.scenario.harga_intervensi)
    else:
        sim_harga = original_harga * (1 + (req.scenario.pct_shock or 0) / 100)  # type: ignore[operator]

    # 4. Build simulated feature row
    sim_row = row.copy()
    sim_row["harga_aktual"] = sim_harga

    lag_1d       = float(row.get("harga_lag_1d",    sim_harga) or sim_harga)
    lag_7d       = float(row.get("harga_lag_7d",    sim_harga) or sim_harga)
    nat_avg      = float(row.get("avg_harga_nasional", sim_harga) or sim_harga)
    roll_avg_30d = float(row.get("rolling_avg_30d", sim_harga) or sim_harga)
    roll_std_30d = float(row.get("rolling_std_30d", 1.0) or 1.0) or 1.0

    sim_row["delta_harga_1d"]       = sim_harga - lag_1d
    sim_row["delta_harga_7d"]       = sim_harga - lag_7d
    sim_row["pct_change_1d"]        = (sim_harga - lag_1d) / lag_1d * 100 if lag_1d else 0.0
    sim_row["pct_change_7d"]        = (sim_harga - lag_7d) / lag_7d * 100 if lag_7d else 0.0
    sim_row["harga_ratio_nasional"] = sim_harga / nat_avg if nat_avg else 1.0
    sim_row["harga_zscore_30d"]     = (sim_harga - roll_avg_30d) / roll_std_30d

    # 5. Lapis 1 — predictions on modified row
    sim_p50_7d,  sim_p90_7d  = pipeline._predict(sim_row, horizon=7)
    sim_p50_14d, sim_p90_14d = pipeline._predict(sim_row, horizon=14)

    # 6. Lapis 2 — detection on modified row
    sim_detection = None
    if pipeline._df is not None and not pipeline._df.empty:
        day_df = pipeline._df[
            (pipeline._df["komoditas_nama"] == req.komoditas_nama) &
            (pipeline._df["tanggal"] == pd.Timestamp(req.tanggal))
        ].copy()
        # Inject simulated price for this kota in day_df
        day_df.loc[day_df["kota_nama"] == req.kota_nama, "harga_aktual"] = sim_harga

        sim_detection = run_detection(
            row=sim_row,
            history_df=history_df,
            day_df=day_df,
            pred_p50=sim_p50_7d,
            pred_p90=sim_p90_7d,
        )

    # 7. Lapis 3 — optional LLM for simulated scenario only
    sim_decision = None
    if req.with_llm and sim_detection and pipeline._agent:
        sim_decision = pipeline._agent.decide(sim_detection)

    # 8. Build result objects
    baseline = FullAnalysisResult(
        komoditas_nama=req.komoditas_nama,
        kota_nama=req.kota_nama,
        tanggal=req.tanggal,
        pred_p50_7d=base_p50_7d,
        pred_p90_7d=base_p90_7d,
        pred_p50_14d=base_p50_14d,
        pred_p90_14d=base_p90_14d,
        detection=base_detection,
    )
    sim_result = FullAnalysisResult(
        komoditas_nama=req.komoditas_nama,
        kota_nama=req.kota_nama,
        tanggal=req.tanggal,
        pred_p50_7d=sim_p50_7d,
        pred_p90_7d=sim_p90_7d,
        pred_p50_14d=sim_p50_14d,
        pred_p90_14d=sim_p90_14d,
        detection=sim_detection,
        decision=sim_decision,
    )

    # 9. Delta summary
    b_p50 = base_p50_7d or 0.0
    s_p50 = sim_p50_7d or 0.0

    delta: dict[str, Any] = {
        "harga_delta":          round(sim_harga - original_harga, 2),
        "harga_pct_change":     round((sim_harga - original_harga) / original_harga * 100, 2) if original_harga else 0.0,
        "p50_7d_delta":         round(s_p50 - b_p50, 2),
        "p50_7d_pct_change":    round((s_p50 - b_p50) / b_p50 * 100, 2) if b_p50 else 0.0,
        "alert_level_changed":  baseline.final_alert_level != sim_result.final_alert_level,
        "baseline_alert":       baseline.final_alert_level,
        "simulated_alert":      sim_result.final_alert_level,
    }

    return {
        "komoditas_nama": req.komoditas_nama,
        "kota_nama":      req.kota_nama,
        "tanggal":        str(req.tanggal),
        "scenario": {
            "harga_original": round(original_harga, 2),
            "harga_simulasi": round(sim_harga, 2),
            "type": "harga_intervensi" if req.scenario.harga_intervensi is not None else "pct_shock",
        },
        "baseline":  _serialize_result(baseline),
        "simulated": _serialize_result(sim_result),
        "delta":     delta,
    }


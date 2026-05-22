"""
ML Proxy Routes — Proxy requests to ML Inference Server (port 8001).

Main FastAPI (port 8000) acts as API gateway, forwarding ML requests
to the dedicated ML server. Frontend only needs to talk to one server.

Endpoints:
  POST /api/ml/analyze         - Analisis tunggal (komoditas, kota, tanggal)
  POST /api/ml/batch           - Batch analisis multiple requests
  GET  /api/ml/alerts          - Alert aktif pada tanggal tertentu
  GET  /api/ml/summary/{date}  - Ringkasan harian (red/yellow/green counts)
  GET  /api/ml/komoditas       - Daftar komoditas tersedia di ML pipeline
  GET  /api/ml/kota            - Daftar kota tersedia di ML pipeline
  GET  /api/ml/health          - Health check ML server
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import _current_user

# ML server base URL — allow localhost and Docker service names (internal network)
_raw_url = os.environ.get("ML_SERVER_URL", "http://localhost:8001")

# Allow localhost, 127.0.0.1, and internal Docker service names (e.g. http://ml-model:8001)
_ALLOWED_PREFIXES = ("http://localhost", "http://127.0.0.1")
_ALLOWED_DOCKER_HOSTS = ("ml-model",)

_is_allowed = (
    _raw_url.startswith(_ALLOWED_PREFIXES)
    or any(_raw_url.startswith(f"http://{h}") for h in _ALLOWED_DOCKER_HOSTS)
)
if not _is_allowed:
    raise ValueError(
        f"ML_SERVER_URL must point to localhost or allowed Docker service, got: {_raw_url}"
    )
ML_SERVER_URL = _raw_url.rstrip("/")

ml_router = APIRouter(prefix="/api/ml", tags=["ML Predictions"])


# ── Request Models ────────────────────────────────────────────────────────────

class MLAnalyzeRequest(BaseModel):
    komoditas_nama: str = Field(..., example="Cabai Merah Keriting")
    kota_nama: str = Field(..., example="Bandung")
    tanggal: date = Field(default_factory=date.today)


class MLBatchRequest(BaseModel):
    requests: list[MLAnalyzeRequest]
    tanggal: Optional[date] = None  # override all request dates if set


# ── HTTP Client Helper ────────────────────────────────────────────────────────

async def _proxy_get(path: str, params: dict | None = None) -> Any:
    """Forward GET request to ML server."""
    import httpx

    url = f"{ML_SERVER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="ML server tidak tersedia. Pastikan ML inference server berjalan di port 8001.",
        )
    except httpx.HTTPStatusError as exc:
        # Sanitize upstream error — don't leak internal stack traces
        detail = f"ML server error: {exc.response.status_code}"
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="ML server timeout. Proses analisis mungkin terlalu lama.",
        )


async def _proxy_post(path: str, json_body: dict) -> Any:
    """Forward POST request to ML server."""
    import httpx

    url = f"{ML_SERVER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=json_body)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="ML server tidak tersedia. Pastikan ML inference server berjalan di port 8001.",
        )
    except httpx.HTTPStatusError as exc:
        # Sanitize upstream error — don't leak internal stack traces
        detail = f"ML server error: {exc.response.status_code}"
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="ML server timeout. Proses analisis mungkin terlalu lama.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@ml_router.get("/health", summary="Health check ML server")
async def ml_health() -> dict:
    """Check if ML inference server is running and models are loaded."""
    return await _proxy_get("/health")


@ml_router.post("/analyze", summary="Analisis ML tunggal")
async def ml_analyze(req: MLAnalyzeRequest, user: dict = Depends(_current_user)) -> dict:
    """
    Jalankan full 3-layer ML analysis untuk satu (komoditas, kota, tanggal).

    - Lapis 1: Prediksi harga 7 & 14 hari ke depan (Q50/Q90)
    - Lapis 2: Deteksi changepoint + HET alert
    - Lapis 3: LLM reasoning -> rekomendasi intervensi
    """
    return await _proxy_post("/api/v1/analyze", {
        "komoditas_nama": req.komoditas_nama,
        "kota_nama": req.kota_nama,
        "tanggal": str(req.tanggal),
    })


@ml_router.post("/batch", summary="Batch analisis ML")
async def ml_batch(req: MLBatchRequest, user: dict = Depends(_current_user)) -> list[dict]:
    """Batch analisis untuk multiple (komoditas, kota) sekaligus."""
    body = {
        "requests": [
            {
                "komoditas_nama": r.komoditas_nama,
                "kota_nama": r.kota_nama,
                "tanggal": str(r.tanggal),
            }
            for r in req.requests
        ],
    }
    if req.tanggal:
        body["tanggal"] = str(req.tanggal)
    return await _proxy_post("/api/v1/batch", body)


@ml_router.get("/alerts", summary="Alert ML aktif")
async def ml_alerts(
    tanggal: Optional[date] = Query(default=None, description="Tanggal analisis"),
    min_alert_level: str = Query(
        default="yellow", pattern="^(yellow|red)$",
        description="Minimum alert level",
    ),
    user: dict = Depends(_current_user),
) -> dict:
    """Semua alert aktif pada tanggal tertentu, diurutkan priority."""
    params: dict[str, str] = {"min_alert_level": min_alert_level}
    if tanggal:
        params["tanggal"] = str(tanggal)
    return await _proxy_get("/api/v1/alerts", params=params)


@ml_router.get("/summary/{tanggal}", summary="Ringkasan harian ML")
async def ml_summary(tanggal: date, user: dict = Depends(_current_user)) -> dict:
    """
    Ringkasan harian: jumlah red/yellow/green, komoditas paling berisiko.
    Berguna untuk tampilan homepage dashboard.
    """
    return await _proxy_get(f"/api/v1/summary/{tanggal}")


@ml_router.get("/komoditas", summary="Daftar komoditas ML")
async def ml_komoditas(user: dict = Depends(_current_user)) -> dict:
    """Daftar komoditas yang tersedia di ML pipeline."""
    return await _proxy_get("/api/v1/komoditas")


@ml_router.get("/kota", summary="Daftar kota ML")
async def ml_kota(user: dict = Depends(_current_user)) -> dict:
    """Daftar kota yang tersedia di ML pipeline."""
    return await _proxy_get("/api/v1/kota")

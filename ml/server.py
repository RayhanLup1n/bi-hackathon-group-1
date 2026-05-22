"""
R.A.D.A.R Pangan - ML Inference Server Template

This is a template for the ML inference server. ML teammate should
customize this to match their model.

Contract:
    - Expose port 8001
    - POST /predict  -> price predictions
    - GET  /health   -> {"status": "ok"}

FastAPI app (port 8000) proxies requests to this server via /api/ml/*

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="R.A.D.A.R Pangan ML Model",
    description="Price prediction inference server",
)


# -- Request/Response schemas --

class PredictionRequest(BaseModel):
    komoditas_id: str      # e.g. "com_13" (Cabai Merah Besar)
    kota_id: int           # e.g. 3273 (Kota Bandung)
    horizon_days: int = 7  # how many days ahead to predict


class PredictionItem(BaseModel):
    target_date: str
    predicted_price: float
    confidence_lower: float
    confidence_upper: float


class PredictionResponse(BaseModel):
    komoditas_id: str
    kota_id: int
    model_version: str
    predictions: list[PredictionItem]


# -- Endpoints --

@app.get("/health")
def health():
    """Liveness check - used by Docker healthcheck."""
    return {"status": "ok", "model_loaded": False}


@app.post("/predict", response_model=PredictionResponse)
def predict(req: PredictionRequest):
    """
    Generate price predictions.

    TODO: ML teammate - replace this stub with actual model inference.
    """
    # Stub response - replace with actual model prediction
    raise HTTPException(
        status_code=501,
        detail="Model not implemented yet. Replace server.py with actual inference logic.",
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MODEL_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)

# ========================================
# Dockerfile - R.A.D.A.R Pangan ML Model
# 3-layer ML inference server:
#   Lapis 1: LightGBM Quantile Forecast
#   Lapis 2: Bayesian Changepoint + HET Detection
#   Lapis 3: LLM Reasoning Agent
#
# Contract:
#   - Expose port 8001
#   - GET  /health            -> pipeline status
#   - POST /api/v1/analyze    -> single analysis
#   - POST /api/v1/batch      -> batch analysis
#   - GET  /api/v1/alerts     -> active alerts
#   - GET  /api/v1/summary/*  -> daily summary
#   - GET  /api/v1/komoditas  -> available commodities
#   - GET  /api/v1/kota       -> available cities
# ========================================

FROM python:3.11-slim

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# WORKDIR is one level above ml/ so that `from ml.src.*` imports resolve
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/ml/requirements.txt
RUN pip install --no-cache-dir -r /app/ml/requirements.txt

# Copy ML package into /app/ml/
COPY . /app/ml/

EXPOSE 8001

# Entry point: uvicorn with module path ml.serve.api
CMD ["uvicorn", "ml.serve.api:app", "--host", "0.0.0.0", "--port", "8001"]

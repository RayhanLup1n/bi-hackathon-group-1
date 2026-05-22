# ========================================
# Dockerfile - R.A.D.A.R Pangan App
# FastAPI backend + frontend static files
# Monolith: single container serves API + HTML
#
# Build:  docker compose build app
# Run:    docker compose up app
# ========================================

FROM python:3.11-slim AS base

# System dependencies (psycopg2-binary needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -- Dependency layer (cached unless pyproject.toml or uv.lock changes) --
COPY pyproject.toml uv.lock ./

# Install uv and use it to install deps directly to system Python (no venv needed in container)
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache -r pyproject.toml

# -- Application layer --
COPY main.py ./
COPY config/ ./config/
COPY src/ ./src/
COPY frontend/ ./frontend/

# Create .envs directory (actual .env mounted at runtime via volume or env_file)
RUN mkdir -p .envs

EXPOSE 8000

# Health check: lightweight endpoint, no DB dependency
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# Run uvicorn directly (no venv wrapper needed)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

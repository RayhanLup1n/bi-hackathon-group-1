# ========================================
# Dockerfile - R.A.D.A.R Pangan App
# FastAPI backend + frontend static files
# DB: Supabase PostgreSQL (cloud, external)
# ========================================
FROM python:3.10-slim

# System dependencies for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application code
COPY main.py ./
COPY config/ ./config/
COPY src/ ./src/
COPY frontend/ ./frontend/

# Copy env example (actual .env mounted at runtime)
COPY .envs/.env.example ./.envs/.env.example

EXPOSE 8000

# Run with uv to ensure venv is used
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

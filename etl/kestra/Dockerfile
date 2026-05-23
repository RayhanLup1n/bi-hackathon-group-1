# =============================================================================
# Kestra ETL Orchestrator - R.A.D.A.R Pangan
#
# Custom image: Kestra + Python 3 + dbt-bigquery + ETL dependencies
# Process runner: Python scripts run directly inside this container
#
# Build: docker compose --profile etl build kestra
# Run:   docker compose --profile etl up kestra
# UI:    http://localhost:8080 (admin / kestra)
# =============================================================================

FROM kestra/kestra:v1.3.19

USER root

# -- 1. Install Python 3 + system deps ----------------------------------------
# Note: Kestra v1.3.x base image is Debian-based.
# python3 from default repos is sufficient for our ETL scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# -- 2. Create Python venv for ETL deps (avoids PEP 668 issues) ---------------
RUN python3 -m venv /opt/etl-venv
ENV PATH="/opt/etl-venv/bin:$PATH"

# -- 3. Install ETL Python dependencies ---------------------------------------
RUN pip install --no-cache-dir \
    # HTTP client + scraping
    httpx \
    beautifulsoup4 \
    lxml \
    # Data processing
    pandas \
    numpy \
    # Database drivers
    psycopg2-binary \
    google-cloud-bigquery \
    db-dtypes \
    # dbt (BigQuery adapter includes dbt-core + pyarrow)
    "dbt-bigquery>=1.8.0" \
    # Config + utilities
    python-dotenv \
    loguru \
    tenacity \
    holidays \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.3.0"

# -- 4. Verify Python + dbt are installed correctly ----------------------------
RUN python3 --version && dbt --version

# -- 5. Working directory for mounted project code ----------------------------
# Project root mounted at /app/project via docker-compose volume
WORKDIR /app

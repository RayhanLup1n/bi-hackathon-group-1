# ========================================
# Dockerfile untuk BI PIHPS Pipeline
# Base : Apache Airflow 2.9.2 (Python 3.11, Debian Bookworm)
# Stack: Airflow + dbt-postgres + Playwright (fallback scraper)
# Data target: Supabase PostgreSQL (cloud)
# ========================================
FROM apache/airflow:2.9.2-python3.11

# ── 1. System dependencies (sebagai root) ────────────────────────────────────
USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    curl \
    gcc \
    libpq-dev \
    # Playwright / Chromium runtime deps
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    # libasound2: di Bookworm lama namanya "libasound2", di Bookworm baru "libasound2t64"
    # Pakai conditional agar kompatibel dengan keduanya
    && (apt-get install -y --no-install-recommends libasound2t64 2>/dev/null \
        || apt-get install -y --no-install-recommends libasound2) \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 2. Install uv sebagai binary standalone (lebih cepat, tidak perlu pip) ───
# Taruh di /usr/local/bin agar tersedia untuk semua user
RUN curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin sh

# ── 3. Pindah ke airflow user untuk install dependencies ─────────────────────
USER airflow

WORKDIR /opt/airflow

# Copy pyproject.toml lebih dulu (layer cache: jika tidak berubah, skip install)
COPY --chown=airflow:root pyproject.toml /opt/airflow/pyproject.toml

# Install semua dependencies langsung ke Python Airflow (pip install --user)
# Ini memastikan Airflow tasks bisa menemukan semua package kita
# uv digunakan sebagai installer yang cepat, tapi target-nya Python system bukan venv
RUN pip install --no-cache-dir \
        httpx \
        beautifulsoup4 \
        lxml \
        playwright \
        pandas \
        psycopg2-binary \
        "dbt-core>=1.8.0" \
        "dbt-postgres>=1.8.0" \
        python-dotenv \
        loguru \
        tenacity \
        holidays \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.3.0"

# ── 4. Install Playwright browser (Chromium) ─────────────────────────────────
# Chromium saja sudah cukup (lebih ringan dari Firefox/WebKit)
RUN playwright install chromium

# ── 5. Copy source code project ──────────────────────────────────────────────
COPY --chown=airflow:root . /opt/airflow/

# Buat direktori data (untuk logs dan temporary files)
RUN mkdir -p /opt/airflow/data

WORKDIR /opt/airflow

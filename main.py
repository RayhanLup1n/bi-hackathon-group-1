import base64
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

# Configure logging before anything else
logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Load environment variables from .envs/.env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".envs", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def _setup_gcp_credentials() -> None:
    """Decode base64-encoded GCP service account JSON from env var.

    Cloud platforms (Railway, Render, Cloud Run) can't mount files,
    so we accept GOOGLE_CREDENTIALS_BASE64 and write it to a temp file.
    Sets GOOGLE_APPLICATION_CREDENTIALS to the temp file path.

    Priority:
      1. GOOGLE_APPLICATION_CREDENTIALS already set → skip
      2. GOOGLE_CREDENTIALS_BASE64 set → decode, write, set path
      3. Neither → skip (BigQuery won't be available)
    """
    import json

    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
    if not creds_b64:
        logger.info("No GCP credentials configured — BigQuery features disabled")
        return

    try:
        creds_json = base64.b64decode(creds_b64)
        # Validate JSON structure before writing
        parsed = json.loads(creds_json)
        if parsed.get("type") != "service_account":
            logger.warning("GOOGLE_CREDENTIALS_BASE64 is not a service_account JSON — skipping")
            return

        # Write to temp file (persists for process lifetime)
        fd, path = tempfile.mkstemp(suffix=".json", prefix="gcp-sa-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(creds_json)
        except Exception:
            os.close(fd)
            os.unlink(path)
            raise

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        # Remove base64 string from env to avoid leaking via debug endpoints
        os.environ.pop("GOOGLE_CREDENTIALS_BASE64", None)
        logger.info("GCP credentials loaded from GOOGLE_CREDENTIALS_BASE64")
    except Exception as exc:
        logger.warning("Failed to decode GOOGLE_CREDENTIALS_BASE64: %s", exc)


# Load env BEFORE importing modules that read env vars at import time
# (e.g. auth_routes reads JWT_SECRET, DEBUG at module level)
_load_env()
_setup_gcp_credentials()

# Now safe to import app modules that depend on env vars
from src.api.routes import router, het_router, cuaca_router, stok_router, predictions_router, data_quality_router  # noqa: E402
from src.api.auth_routes import auth_router  # noqa: E402
from src.api.ml_routes import ml_router  # noqa: E402
from src.api.mvp_routes import mvp_router  # noqa: E402
from src.api.errors import AppError  # noqa: E402
from src.api.middleware.rate_limiter import limiter  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database connections and seed data at startup."""
    from src.infrastructure.postgres.database import init_pool, close_pool
    from src.infrastructure.postgres.commodity_data import init_commodity_data
    from src.infrastructure.postgres.auth_db import init_db_auth

    # Initialize connection pool to Supabase PostgreSQL (Gold layer -- all app data)
    init_pool()

    # Verify database connectivity
    from src.infrastructure.postgres.database import get_conn, release_conn
    try:
        conn = get_conn()
        conn.cursor().execute("SELECT 1")
        release_conn(conn)
        logger.info("Database connection verified")
        app.state.db_healthy = True
    except Exception as exc:
        logger.critical("Database health check failed: %s", exc)
        app.state.db_healthy = False
        # App continues — endpoints throw ServiceUnavailableError if DB is down

    # Load commodity mapping from Supabase PostgreSQL (app.harga_pangan)
    init_commodity_data()

    # Seed default users if empty (Supabase)
    init_db_auth()

    # BigQuery client is NOT initialized here -- only used by ETL scripts
    # and admin-only data quality endpoints (lazy init in data_quality.py)

    yield

    # Cleanup on shutdown
    close_pool()
    # Close BigQuery client if it was initialized
    from src.infrastructure.bigquery.bigquery_client import close_bq_client
    close_bq_client()
    # Remove temp GCP credentials file if it was created
    _gcp_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if _gcp_path and _gcp_path.startswith(tempfile.gettempdir()):
        try:
            os.unlink(_gcp_path)
            logger.debug("Cleaned up temp GCP credentials file")
        except OSError:
            pass


_DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
# Separate toggle for API docs — allow Swagger in production demos without DEBUG mode
_ENABLE_DOCS = _DEBUG or os.environ.get("ENABLE_DOCS", "false").lower() == "true"

app = FastAPI(
    title="R.A.D.A.R Pangan",
    version="0.7.0",
    description=(
        "Real-time Anti-inflation Detection, Analysis & Response. "
        "Platform pemantauan inflasi pangan berbasis data PIHPS."
    ),
    lifespan=lifespan,
    docs_url="/docs" if _ENABLE_DOCS else None,
    redoc_url="/redoc" if _ENABLE_DOCS else None,
    openapi_url="/api/openapi.json" if _ENABLE_DOCS else None,
)

# Attach rate limiter to app state (slowapi reads app.state.limiter)
app.state.limiter = limiter

# CORS middleware - allow same-origin, localhost dev, and production domains
_allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",  # frontend dev server if any
]

# Production origins from env var (comma-separated)
# Example: CORS_ORIGINS=https://my-app.up.railway.app,https://custom-domain.com
_extra_origins = os.environ.get("CORS_ORIGINS", "")
if _extra_origins:
    _allowed_origins.extend(o.strip() for o in _extra_origins.split(",") if o.strip())

# Wildcard subdomain patterns — Starlette CORSMiddleware uses
# allow_origin_regex for pattern matching (not glob in allow_origins)
_origin_regex = r"https://.*\.(up\.railway\.app|ngrok-free\.app)$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # CSP: allow inline scripts (Alpine.js), CDN for Chart.js/Swagger, self for everything else
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "connect-src 'self' https://web-production-1eea6.up.railway.app"
    )
    return response

# Request timing middleware — log slow API endpoints for debugging
@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    """Log request method, path, status, and duration for all API endpoints."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Only log API routes (skip static files, health checks)
    if request.url.path.startswith("/api"):
        level = logging.WARNING if elapsed_ms > 2000 else logging.INFO
        logger.log(
            level,
            "[%s] %s %s — %d — %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response


app.include_router(router)
app.include_router(het_router)
app.include_router(cuaca_router)
app.include_router(stok_router)
app.include_router(predictions_router)
app.include_router(auth_router)
app.include_router(ml_router)
app.include_router(data_quality_router)
app.include_router(mvp_router)


# ── Exception handlers ────────────────────────────────────────────────────

@app.exception_handler(AppError)
async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError subclasses to proper HTTP error responses."""
    if exc.internal_message:
        logger.error(
            "AppError %d: %s | internal=%s",
            exc.status_code,
            exc.detail,
            exc.internal_message,
        )
    else:
        logger.warning("AppError %d: %s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 Too Many Requests when rate limit is exceeded."""
    logger.warning("Rate limit exceeded: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Terlalu banyak permintaan. Silakan coba lagi nanti."},
        headers={"Retry-After": str(exc.retry_after) if getattr(exc, "retry_after", None) else "60"},
    )


@app.get("/health", tags=["system"])
def health():
    """Liveness check for Docker healthcheck and load balancers.
    Does NOT check database - use /api/status for deep health check.
    """
    return {"status": "ok", "service": "radar-pangan"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return empty favicon to suppress 404 errors."""
    return Response(content=b"", media_type="image/x-icon")

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    # Serve /assets/ directory (logo, images)
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    # Serve CSS directory
    css_dir = os.path.join(frontend_dir, "css")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")

    def _html(filename: str) -> FileResponse:
        """Serve HTML file with no-cache headers to prevent stale content."""
        resp = FileResponse(os.path.join(frontend_dir, filename))
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return _html("index.html")

    @app.get("/config.js", include_in_schema=False)
    def serve_config_js():
        """Serve runtime config JS at root path for HTML pages."""
        return FileResponse(os.path.join(frontend_dir, "config.js"))

    @app.get("/login", include_in_schema=False)
    def serve_login():
        return _html("login.html")

    @app.get("/admin", include_in_schema=False)
    def serve_admin():
        return _html("admin.html")

    @app.get("/analysis", include_in_schema=False)
    def serve_analysis():
        return _html("rca.html")

    @app.get("/prediksi", include_in_schema=False)
    def serve_prediksi():
        return _html("prediksi.html")

    @app.get("/guide", include_in_schema=False)
    def serve_guide():
        return _html("guide.html")

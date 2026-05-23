from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from src.api.routes import router, het_router, cuaca_router, stok_router, predictions_router, data_quality_router
from src.api.auth_routes import auth_router
from src.api.ml_routes import ml_router

import os


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


# Load env before anything else
_load_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database connections and seed data at startup."""
    from src.data.database import init_pool, close_pool
    from src.data.commodity_data import init_commodity_data
    from src.data.auth_db import init_db_auth

    # Initialize connection pool to Supabase PostgreSQL (Gold layer -- all app data)
    init_pool()

    # Load commodity mapping from Supabase PostgreSQL (app.harga_pangan)
    init_commodity_data()

    # Seed default users if empty (Supabase)
    init_db_auth()

    # BigQuery client is NOT initialized here -- only used by ETL scripts
    # and admin-only data quality endpoints (lazy init in data_quality.py)

    yield

    # Cleanup on shutdown
    close_pool()


app = FastAPI(
    title="R.A.D.A.R Pangan",
    description=(
        "Real-time Anti-inflation Detection, Analysis & Response. "
        "Platform pemantauan inflasi pangan berbasis data PIHPS."
    ),
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(het_router)
app.include_router(cuaca_router)
app.include_router(stok_router)
app.include_router(predictions_router)
app.include_router(auth_router)
app.include_router(ml_router)
app.include_router(data_quality_router)


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

    @app.get("/login", include_in_schema=False)
    def serve_login():
        return _html("login.html")

    @app.get("/admin", include_in_schema=False)
    def serve_admin():
        return _html("admin.html")

    @app.get("/rca", include_in_schema=False)
    def serve_rca():
        return _html("rca.html")

    @app.get("/prediksi", include_in_schema=False)
    def serve_prediksi():
        return _html("prediksi.html")

    @app.get("/guide", include_in_schema=False)
    def serve_guide():
        return _html("guide.html")

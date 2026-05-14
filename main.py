from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from src.api.routes import router, het_router, cuaca_router, stok_router, predictions_router
from src.api.auth_routes import auth_router

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

    # Initialize connection pool to Supabase PostgreSQL
    init_pool()

    # Load commodity mapping from database
    init_commodity_data()

    # Seed default users if empty
    init_db_auth()

    yield

    # Cleanup on shutdown
    close_pool()


app = FastAPI(
    title="R.A.D.A.R Pangan",
    description=(
        "Real-time Anti-inflation Detection, Analysis & Response. "
        "Platform pemantauan inflasi pangan berbasis data PIHPS."
    ),
    version="0.4.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(het_router)
app.include_router(cuaca_router)
app.include_router(stok_router)
app.include_router(predictions_router)
app.include_router(auth_router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return empty favicon to suppress 404 errors."""
    return Response(content=b"", media_type="image/x-icon")

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/login", include_in_schema=False)
    def serve_login():
        return FileResponse(os.path.join(frontend_dir, "login.html"))

    @app.get("/admin", include_in_schema=False)
    def serve_admin():
        return FileResponse(os.path.join(frontend_dir, "admin.html"))

    @app.get("/rca", include_in_schema=False)
    def serve_rca():
        return FileResponse(os.path.join(frontend_dir, "rca.html"))

    @app.get("/prediksi", include_in_schema=False)
    def serve_prediksi():
        return FileResponse(os.path.join(frontend_dir, "prediksi.html"))

    @app.get("/guide", include_in_schema=False)
    def serve_guide():
        return FileResponse(os.path.join(frontend_dir, "guide.html"))

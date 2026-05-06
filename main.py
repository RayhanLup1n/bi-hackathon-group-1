from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.api.routes import router, bmkg_router, stok_router
from src.api.auth_routes import auth_router
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inisialisasi semua DB simulasi saat startup (idempoten)."""
    from src.data.bmkg_db import init_db
    from src.data.stok_db import init_db_stok
    from src.data.auth_db import init_db_auth
    init_db()
    init_db_stok()
    init_db_auth()
    yield


app = FastAPI(
    title="RCA RadarPangan",
    description=(
        "Root Cause Analysis engine untuk anomali harga pangan Indonesia. "
        "Dilengkapi simulasi database BMKG untuk data cuaca & peringatan ekstrem."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(bmkg_router)
app.include_router(stok_router)
app.include_router(auth_router)

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

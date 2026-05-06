"""
src/api/auth_routes.py
======================
Endpoint autentikasi dan manajemen pengguna.

Endpoints
---------
POST /api/auth/login           → login, kembalikan JWT
GET  /api/auth/me              → data user yang sedang login
GET  /api/auth/users           → daftar semua users (admin only)
POST /api/auth/users           → tambah user baru (admin only)
PATCH /api/auth/users/{id}     → edit password / role (admin only)
DELETE /api/auth/users/{id}    → hapus user (admin only)
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from src.data.auth_db import (
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    update_user,
    verify_password,
)

_SECRET = "radarpangan-secret-key-change-in-production"
_ALGO = "HS256"
_TOKEN_HOURS = 8

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Pydantic models ────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=_TOKEN_HOURS)
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        _SECRET,
        algorithm=_ALGO,
    )


def _current_user(token: str = Depends(_oauth2)) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        username: str = payload.get("sub", "")
        if not username:
            raise exc
    except JWTError:
        raise exc
    user = get_user_by_username(username)
    if not user:
        raise exc
    return user


def _require_admin(user: dict = Depends(_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@auth_router.post("/login", summary="Login dan dapatkan JWT")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form.username)
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    return {
        "access_token": _make_token(user["username"], user["role"]),
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
    }


@auth_router.get("/me", summary="Data user yang sedang login")
def get_me(user: dict = Depends(_current_user)):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@auth_router.get("/users", summary="Daftar semua users (admin only)")
def get_users(_: dict = Depends(_require_admin)):
    return list_users()


@auth_router.post("/users", status_code=201, summary="Tambah user baru (admin only)")
def add_user(data: UserCreate, _: dict = Depends(_require_admin)):
    if data.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=422, detail="Role harus: admin, analyst, atau viewer")
    try:
        return create_user(data.username, data.password, data.role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@auth_router.patch("/users/{user_id}", summary="Edit password / role (admin only)")
def patch_user(user_id: int, data: UserUpdate, _: dict = Depends(_require_admin)):
    if data.role and data.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=422, detail="Role harus: admin, analyst, atau viewer")
    result = update_user(user_id, data.password or None, data.role or None)
    if not result:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return result


@auth_router.delete("/users/{user_id}", status_code=204, summary="Hapus user (admin only)")
def remove_user(user_id: int, current: dict = Depends(_require_admin)):
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="Tidak bisa menghapus akun sendiri")
    delete_user(user_id)

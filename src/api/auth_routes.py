"""
src/api/auth_routes.py
======================
Endpoint autentikasi dan manajemen pengguna.

Auth menggunakan boolean flags (is_admin, is_analyst, is_active) bukan role string.
Backward-compat: computed "role" field tetap disertakan di response.

Endpoints
---------
POST /api/auth/login           → login, kembalikan JWT
GET  /api/auth/me              → data user yang sedang login
GET  /api/auth/users           → daftar semua users (admin only)
POST /api/auth/users           → tambah user baru (admin only)
PATCH /api/auth/users/{id}     → edit password / flags (admin only)
DELETE /api/auth/users/{id}    → hapus user (admin only)
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

import os

from src.data.auth_db import (
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    update_user,
    verify_password,
)

# JWT secret from env var — required in production, dev fallback only if DEBUG=true
_DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
_SECRET = os.environ.get("JWT_SECRET", "")

if not _SECRET:
    if _DEBUG:
        _SECRET = "radarpangan-dev-secret-DO-NOT-USE-IN-PROD"
    else:
        raise RuntimeError(
            "JWT_SECRET env var is required. "
            "Set JWT_SECRET (min 32 chars) or set DEBUG=true for dev mode."
        )

if len(_SECRET) < 32 and not _DEBUG:
    raise RuntimeError(
        f"JWT_SECRET too short ({len(_SECRET)} chars). Minimum 32 chars required."
    )

_ALGO = "HS256"
_TOKEN_HOURS = 8

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Pydantic models ────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    is_analyst: bool = False


class UserUpdate(BaseModel):
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_analyst: Optional[bool] = None
    is_active: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(user: dict) -> str:
    """Create JWT with boolean flags + computed role for backward compat."""
    expire = datetime.utcnow() + timedelta(hours=_TOKEN_HOURS)
    return jwt.encode(
        {
            "sub": user["username"],
            "role": user["role"],  # computed by auth_db._compute_role
            "is_admin": user.get("is_admin", False),
            "is_analyst": user.get("is_analyst", False),
            "exp": expire,
        },
        _SECRET,
        algorithm=_ALGO,
    )


def _user_response(user: dict) -> dict:
    """Build consistent user response dict (no password_hash)."""
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "viewer"),
        "is_admin": user.get("is_admin", False),
        "is_analyst": user.get("is_analyst", False),
        "is_active": user.get("is_active", True),
    }


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
    # Check if account is disabled
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan")
    return user


def _require_admin(user: dict = Depends(_current_user)) -> dict:
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@auth_router.post("/login", summary="Login dan dapatkan JWT")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form.username)
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    # Block disabled accounts from logging in
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan")
    return {
        "access_token": _make_token(user),
        "token_type": "bearer",
        "user": _user_response(user),
    }


@auth_router.get("/me", summary="Data user yang sedang login")
def get_me(user: dict = Depends(_current_user)):
    return _user_response(user)


@auth_router.get("/users", summary="Daftar semua users (admin only)")
def get_users(_: dict = Depends(_require_admin)):
    return list_users()


@auth_router.post("/users", status_code=201, summary="Tambah user baru (admin only)")
def add_user(data: UserCreate, _: dict = Depends(_require_admin)):
    try:
        return create_user(
            data.username,
            data.password,
            is_admin=data.is_admin,
            is_analyst=data.is_analyst,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@auth_router.patch("/users/{user_id}", summary="Edit password / flags (admin only)")
def patch_user(user_id: int, data: UserUpdate, _: dict = Depends(_require_admin)):
    result = update_user(
        user_id,
        new_password=data.password or None,
        is_admin=data.is_admin,
        is_analyst=data.is_analyst,
        is_active=data.is_active,
    )
    if not result:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return result


@auth_router.delete("/users/{user_id}", status_code=204, summary="Hapus user (admin only)")
def remove_user(user_id: int, current: dict = Depends(_require_admin)):
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="Tidak bisa menghapus akun sendiri")
    delete_user(user_id)

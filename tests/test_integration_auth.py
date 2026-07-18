"""
Integration tests for auth endpoints using FastAPI TestClient.

Tests auth flows: login, token validation, role guards, CRUD operations.
Patches database startup so no real database connection is required.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# ── Patch DB before importing app (prevents psycopg2 connect) ───────────────

from contextlib import asynccontextmanager  # noqa: E402

patch("src.infrastructure.postgres.database.init_pool", return_value=None).start()

from main import app  # noqa: E402


# Replace lifespan with no-op to skip startup/shutdown
@asynccontextmanager
async def _noop_lifespan(app_ref):
    yield

app.router.lifespan_context = _noop_lifespan

# ── Token helpers ───────────────────────────────────────────────────────────

_SECRET = os.environ.get("JWT_SECRET", "integration-test-secret-32-chars-long!!")
_ALGO = "HS256"


def _make_token(username: str, is_admin: bool = False, is_analyst: bool = False,
                expired: bool = False) -> str:
    """Create a valid JWT for testing."""
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=8)
    return jwt.encode(
        {
            "sub": username,
            "role": "admin" if is_admin else ("analyst" if is_analyst else "viewer"),
            "is_admin": is_admin,
            "is_analyst": is_analyst,
            "iat": now,
            "exp": exp,
        },
        _SECRET,
        algorithm=_ALGO,
    )


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Mock user fixtures ──────────────────────────────────────────────────────

def _admin_user() -> dict:
    return {
        "id": 1, "username": "admin", "role": "admin",
        "is_admin": True, "is_analyst": False, "is_active": True,
        "password_hash": "$2b$12$LJ3m4ys3Lk0TSwHCpNqrlu5YKVEBhqKeJFbQuIFzVgeInQHQFu0eK",
    }


def _analyst_user() -> dict:
    return {
        "id": 2, "username": "analyst", "role": "analyst",
        "is_admin": False, "is_analyst": True, "is_active": True,
        "password_hash": "$2b$12$LJ3m4ys3Lk0TSwHCpNqrlu5YKVEBhqKeJFbQuIFzVgeInQHQFu0eK",
    }


def _inactive_user() -> dict:
    return {
        "id": 3, "username": "disabled", "role": "viewer",
        "is_admin": False, "is_analyst": False, "is_active": False,
        "password_hash": "$2b$12$LJ3m4ys3Lk0TSwHCpNqrlu5YKVEBhqKeJFbQuIFzVgeInQHQFu0eK",
    }


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient with mocked auth layer."""
    with TestClient(app) as c:
        yield c


# ── Auth login tests ────────────────────────────────────────────────────────

class TestAuthLogin:
    """Login endpoint tests."""

    @pytest.mark.integration
    def test_login_success(self, client):
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.verify_password",
            return_value=True,
        ):
            resp = client.post("/api/auth/login", data={
                "username": "admin", "password": "admin123",
            })
            assert resp.status_code == 200
            body = resp.json()
            assert "access_token" in body
            assert body["token_type"] == "bearer"
            assert body["user"]["username"] == "admin"
            assert "password_hash" not in body["user"]

    @pytest.mark.integration
    def test_login_wrong_password(self, client):
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.verify_password",
            return_value=False,
        ):
            resp = client.post("/api/auth/login", data={
                "username": "admin", "password": "wrongpassword",
            })
            assert resp.status_code == 401

    @pytest.mark.integration
    def test_login_nonexistent_user(self, client):
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=None,
        ):
            resp = client.post("/api/auth/login", data={
                "username": "ghost_user", "password": "anything",
            })
            assert resp.status_code == 401

    @pytest.mark.integration
    def test_login_inactive_user_blocked(self, client):
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_inactive_user(),
        ), patch(
            "src.api.auth_routes.verify_password",
            return_value=True,
        ):
            resp = client.post("/api/auth/login", data={
                "username": "disabled", "password": "password",
            })
            assert resp.status_code == 403

    @pytest.mark.integration
    def test_login_missing_username(self, client):
        resp = client.post("/api/auth/login", data={"password": "test"})
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_login_missing_password(self, client):
        resp = client.post("/api/auth/login", data={"username": "test"})
        assert resp.status_code == 422


# ── Token tests ─────────────────────────────────────────────────────────────

class TestTokenValidation:
    """JWT token validation tests."""

    @pytest.mark.integration
    def test_expired_token_rejected(self, client):
        token = _make_token("admin", is_admin=True, expired=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.get("/api/auth/me", headers=_auth_headers(token))
            assert resp.status_code == 401

    @pytest.mark.integration
    def test_malformed_token_rejected(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_no_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_invalid_scheme_rejected(self, client):
        token = _make_token("admin", is_admin=True)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Basic {token}"})
        assert resp.status_code == 401


# ── Role guard tests ────────────────────────────────────────────────────────

class TestRoleGuards:
    """RBAC tests."""

    @pytest.mark.integration
    def test_admin_can_list_users(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.list_users",
            return_value=[{"id": 1, "username": "admin", "role": "admin"}],
        ):
            resp = client.get("/api/auth/users", headers=_auth_headers(token))
            assert resp.status_code == 200

    @pytest.mark.integration
    def test_analyst_cannot_list_users(self, client):
        token = _make_token("analyst", is_analyst=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_analyst_user(),
        ):
            resp = client.get("/api/auth/users", headers=_auth_headers(token))
            assert resp.status_code == 403

    @pytest.mark.integration
    def test_viewer_can_access_health(self, client):
        """Health endpoint is public — no auth needed."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.integration
    def test_viewer_can_access_me(self, client):
        token = _make_token("viewer")
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value={
                "id": 4, "username": "viewer", "role": "viewer",
                "is_admin": False, "is_analyst": False, "is_active": True,
            },
        ):
            resp = client.get("/api/auth/me", headers=_auth_headers(token))
            assert resp.status_code == 200
            assert resp.json()["username"] == "viewer"


# ── User response tests ─────────────────────────────────────────────────────

class TestUserResponse:
    """Verify user response contract."""

    @pytest.mark.integration
    def test_me_no_password_hash(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.get("/api/auth/me", headers=_auth_headers(token))
            body = resp.json()
            assert "password_hash" not in body

    @pytest.mark.integration
    def test_me_has_required_fields(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.get("/api/auth/me", headers=_auth_headers(token))
            body = resp.json()
            for f in ("id", "username", "role", "is_admin", "is_analyst", "is_active"):
                assert f in body, f"Missing: {f}"


# ── User CRUD contract tests ────────────────────────────────────────────────

class TestUserCRUD:
    """User management endpoint tests (admin-only)."""

    @pytest.mark.integration
    def test_create_user_201(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.create_user",
            return_value={"id": 5, "username": "newuser", "role": "viewer",
                          "is_admin": False, "is_analyst": False, "is_active": True},
        ):
            resp = client.post(
                "/api/auth/users",
                json={"username": "newuser", "password": "secure123", "is_analyst": True},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 201

    @pytest.mark.integration
    def test_short_username_422(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.post(
                "/api/auth/users",
                json={"username": "ab", "password": "secure123"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 422

    @pytest.mark.integration
    def test_weak_password_422(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.post(
                "/api/auth/users",
                json={"username": "newuser", "password": "12"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 422

    @pytest.mark.integration
    def test_update_user_200(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.update_user",
            return_value={"id": 1, "username": "admin", "role": "admin",
                          "is_admin": True, "is_analyst": False, "is_active": True},
        ):
            resp = client.patch(
                "/api/auth/users/1",
                json={"is_analyst": True},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200

    @pytest.mark.integration
    def test_delete_self_blocked(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ):
            resp = client.delete(
                "/api/auth/users/1",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400

    @pytest.mark.integration
    def test_delete_unknown_404(self, client):
        token = _make_token("admin", is_admin=True)
        with patch(
            "src.api.auth_routes.get_user_by_username",
            return_value=_admin_user(),
        ), patch(
            "src.api.auth_routes.delete_user",
            return_value=False,
        ):
            resp = client.delete(
                "/api/auth/users/999",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 404

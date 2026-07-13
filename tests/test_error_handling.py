"""
Tests for custom exception hierarchy and error response mapping.

Verifies each AppError subclass produces correct HTTP status codes
and that the global handler in main.py formats responses correctly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Patch DB before importing app ───────────────────────────────────────────

from contextlib import asynccontextmanager  # noqa: E402

patch("src.infrastructure.postgres.database.init_pool", return_value=None).start()

from main import app  # noqa: E402


@asynccontextmanager
async def _noop_lifespan(app_ref):
    yield


app.router.lifespan_context = _noop_lifespan

from tests.test_integration_auth import _auth_headers, _make_token  # noqa: E402

_ADMIN = _auth_headers(_make_token("admin", is_admin=True))
_ANALYST = _auth_headers(_make_token("analyst", is_analyst=True))
from src.api.errors import (  # noqa: E402
    AppError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

client = TestClient(app)


# ── Mock user lookup (avoids real DB calls from _current_user) ──────────────

def _mock_get_user(username: str) -> dict | None:
    users = {
        "admin": {
            "id": 1, "username": "admin", "role": "admin",
            "is_admin": True, "is_analyst": True, "is_active": True,
        },
        "analyst": {
            "id": 2, "username": "analyst", "role": "analyst",
            "is_admin": False, "is_analyst": True, "is_active": True,
        },
    }
    return users.get(username)


@pytest.fixture(autouse=True)
def _patch_auth_db():
    with patch("src.api.auth_routes.get_user_by_username", side_effect=_mock_get_user):
        yield


# ── Unit tests for exception classes ────────────────────────────────────────


class TestAppErrorClasses:
    """Verify each exception class carries the correct status code."""

    def test_app_error_base_defaults_to_500(self):
        exc = AppError("something wrong")
        assert exc.status_code == 500
        assert exc.detail == "something wrong"
        assert exc.internal_message is None

    def test_app_error_with_internal_message(self):
        exc = AppError("public msg", internal_message="secret")
        assert exc.detail == "public msg"
        assert exc.internal_message == "secret"

    def test_not_found_error_has_404(self):
        exc = NotFoundError("komoditas tidak ditemukan")
        assert exc.status_code == 404

    def test_validation_error_has_422(self):
        exc = ValidationError("province invalid")
        assert exc.status_code == 422

    def test_service_unavailable_has_503(self):
        exc = ServiceUnavailableError("db down")
        assert exc.status_code == 503

    def test_conflict_error_has_409(self):
        exc = ConflictError("duplicate entry")
        assert exc.status_code == 409

    def test_app_error_is_exception(self):
        """AppError must be a real Exception for raise/except to work."""
        with pytest.raises(AppError):
            raise AppError("test")

    def test_subclass_is_caught_by_base(self):
        """NotFoundError must be caught by `except AppError`."""
        with pytest.raises(AppError):
            raise NotFoundError("missing")


# ── Integration tests — error responses from routes ─────────────────────────


class TestErrorResponses:
    """Verify routes return correct HTTP status when orchestrator raises typed errors."""

    def test_overview_returns_503_on_db_error(self):
        """When orchestrator raises ServiceUnavailableError, route returns 503."""
        with patch(
            "src.api.mvp_routes.get_overview",
            side_effect=ServiceUnavailableError("DB timeout"),
        ):
            resp = client.get("/api/mvp/overview", headers=_ADMIN)
        assert resp.status_code == 503
        assert "detail" in resp.json()

    def test_priorities_returns_503_on_db_error(self):
        with patch(
            "src.api.mvp_routes.get_priorities",
            side_effect=ServiceUnavailableError("Connection refused"),
        ):
            resp = client.get("/api/mvp/priorities", headers=_ADMIN)
        assert resp.status_code == 503

    def test_priority_detail_not_found(self):
        """When orchestrator returns None, route returns HTTP 404."""
        with patch(
            "src.api.mvp_routes.get_priority_detail",
            return_value=None,
        ):
            resp = client.get(
                "/api/mvp/priorities/nonexistent-id",
                headers=_ADMIN,
            )
        assert resp.status_code == 404
        assert "tidak ditemukan" in resp.json()["detail"].lower()

    def test_priority_detail_503_on_error(self):
        with patch(
            "src.api.mvp_routes.get_priority_detail",
            side_effect=ServiceUnavailableError("DB error"),
        ):
            resp = client.get(
                "/api/mvp/priorities/rec-001",
                headers=_ADMIN,
            )
        assert resp.status_code == 503

    def test_transparency_returns_503_on_error(self):
        with patch(
            "src.api.mvp_routes.get_transparency",
            side_effect=ServiceUnavailableError("timeout"),
        ):
            resp = client.get("/api/mvp/transparency", headers=_ADMIN)
        assert resp.status_code == 503

    def test_service_status_returns_503_on_error(self):
        with patch(
            "src.api.mvp_routes.get_service_status",
            side_effect=ServiceUnavailableError("down"),
        ):
            resp = client.get(
                "/api/mvp/service-status", headers=_ADMIN
            )
        assert resp.status_code == 503

    def test_search_returns_503_on_error(self):
        with patch(
            "src.application.mvp_orchestrator.search_priorities",
            side_effect=ServiceUnavailableError("search failed"),
        ):
            resp = client.get(
                "/api/mvp/search?q=bawang", headers=_ADMIN
            )
        assert resp.status_code == 503

    def test_review_submit_returns_422_on_value_error(self):
        """ValueError in save_review → HTTP 422."""
        # Need to patch both get_priority_detail (returns valid) and save_review (raises)
        with patch(
            "src.api.mvp_routes.get_priority_detail",
            return_value={"id": "rec-001", "komoditas": "Bawang Merah"},
        ), patch(
            "src.infrastructure.postgres.review_repository.save_review",
            side_effect=ValueError("invalid status"),
        ):
            resp = client.post(
                "/api/mvp/priorities/rec-001/review",
                json={"status": "Untuk Dibahas", "note": "test"},
                headers=_ANALYST,
            )
        assert resp.status_code == 422

    def test_error_response_is_json(self):
        """All error responses must have Content-Type: application/json."""
        with patch(
            "src.api.mvp_routes.get_overview",
            side_effect=ServiceUnavailableError("boom"),
        ):
            resp = client.get("/api/mvp/overview", headers=_ADMIN)
        assert resp.headers["content-type"].startswith("application/json")


# ── Health check test ───────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Health endpoint should always respond."""

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_no_auth_required(self):
        """Health endpoint must be accessible without authentication."""
        resp = client.get("/health")
        assert resp.status_code == 200

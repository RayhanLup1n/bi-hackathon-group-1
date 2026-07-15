"""
Integration tests for MVP decision workflow endpoints using FastAPI TestClient.

Tests cover: overview, priorities, detail, search, export, review, transparency,
service status. Uses mocking for the orchestration layer.

Patch strategy:
  - Top-level imports in mvp_routes.py → patch at ``src.api.mvp_routes.<fn>``
  - Local (inline) imports inside route functions → patch at ``src.application.mvp_orchestrator.<fn>``
"""
from __future__ import annotations

import os
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


# ── Mock user lookup (avoids real DB calls from _current_user) ──────────────

def _mock_get_user(username: str) -> dict | None:
    """Return a mock user based on username. Called by patched get_user_by_username."""
    users = {
        "admin": {
            "id": 1, "username": "admin", "role": "admin",
            "is_admin": True, "is_analyst": True, "is_active": True,
        },
        "analyst": {
            "id": 2, "username": "analyst", "role": "analyst",
            "is_admin": False, "is_analyst": True, "is_active": True,
        },
        "viewer": {
            "id": 3, "username": "viewer", "role": "viewer",
            "is_admin": False, "is_analyst": False, "is_active": True,
        },
    }
    return users.get(username)


@pytest.fixture(autouse=True)
def _patch_auth_db():
    """Globally patch get_user_by_username so _current_user resolves without DB."""
    with patch("src.api.auth_routes.get_user_by_username", side_effect=_mock_get_user):
        yield


# ── Mock data builders ──────────────────────────────────────────────────────

def _mock_priority(rec_id: str = "rec_001", commodity: str = "Bawang Merah",
                   risk: str = "kritis", score: float = 92.5,
                   confidence: str = "high") -> dict:
    return {
        "recommendation_id": rec_id, "commodity": commodity, "region": "Nasional",
        "price_condition": "Melampaui Ambang", "risk_level": risk,
        "display_priority_score": score, "raw_priority_score": 98.0,
        "confidence_factor": 0.94, "confidence_level": confidence,
        "time_horizon_days": 7,
        "next_step": "Verifikasi dan koordinasikan eskalsi",
        "knowledge_status": "MODEL_OUTPUT",
        "observed_facts": [{"kind": "FACT", "label": "HET", "value": "130%"}],
        "model_outputs": [{"kind": "MODEL_OUTPUT", "label": "Forecast", "value": "Rp 95,000"}],
        "possible_factors": [],
        "missing_information": ["Kapasitas logistik (data tidak tersedia)"],
        "response_options": [{"type": "VERIFIKASI", "label": "Verifikasi harga", "description": ""}],
        "sources": [{"name": "PIHPS", "cutoff": "2026-07-13"}],
        "priority_signals": {"price_position": 0.9, "forecast_p90_breach": 1.0,
                             "momentum_anomaly": 0.6, "regional_spread": 0.8, "weather_calendar": 0.3},
        "confidence_signals": {"freshness": 0.9, "coverage": 0.8,
                               "history": 0.7, "model_performance": 0.85},
    }


def _mock_overview() -> dict:
    priorities = [
        _mock_priority("rec_001", "Cabai Rawit Merah", "kritis", 92.5),
        _mock_priority("rec_002", "Bawang Merah", "tinggi", 68.0, "medium"),
    ]
    return {
        "region": "Nasional",
        "provinces": [{"id": 11, "name": "Banten"}, {"id": 12, "name": "Jawa Barat"}],
        "data_freshness": {"latest_date": "2026-07-13", "age_days": 0.0,
                           "coverage_ratio": 0.85, "status": "fresh"},
        "service_health": {"database": "ok", "ml_service": "offline"},
        "summary": {"total_commodities": 2,
                    "risk_counts": {"kritis": 1, "tinggi": 1, "sedang": 0, "rendah": 0},
                    "has_critical": True, "has_high": True},
        "top_priorities": priorities,
        "review_bundles": [],
        "latest_reviews": [],
    }


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def viewer_token():
    return _make_token("viewer")


@pytest.fixture
def analyst_token():
    return _make_token("analyst", is_analyst=True)


# ── Overview tests ──────────────────────────────────────────────────────────

class TestMVPOverview:
    @pytest.mark.integration
    def test_overview_shape(self, client, viewer_token):
        # get_overview imported at module level → patch reference in mvp_routes
        with patch("src.api.mvp_routes.get_overview", return_value=_mock_overview()):
            resp = client.get("/api/mvp/overview", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            body = resp.json()
            for key in ("region", "summary", "top_priorities", "data_freshness", "review_bundles"):
                assert key in body

    @pytest.mark.integration
    def test_overview_risk_counts(self, client, viewer_token):
        with patch("src.api.mvp_routes.get_overview", return_value=_mock_overview()):
            resp = client.get("/api/mvp/overview", headers=_auth_headers(viewer_token))
            assert resp.json()["summary"]["risk_counts"]["kritis"] == 1

    @pytest.mark.integration
    def test_overview_requires_auth(self, client):
        assert client.get("/api/mvp/overview").status_code == 401


# ── Priorities tests ───────────────────────────────────────────────────────

class TestMVPPriorities:
    @pytest.mark.integration
    def test_priorities_list(self, client, viewer_token):
        priorities = [_mock_priority("rec_001"), _mock_priority("rec_002", "Bawang Putih", "sedang", 45.0)]
        with patch("src.api.mvp_routes.get_priorities", return_value=priorities):
            resp = client.get("/api/mvp/priorities", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
            assert len(resp.json()) == 2

    @pytest.mark.integration
    def test_priorities_requires_auth(self, client):
        assert client.get("/api/mvp/priorities").status_code == 401


# ── Priority detail tests ──────────────────────────────────────────────────

class TestMVPPriorityDetail:
    @pytest.mark.integration
    def test_detail_found(self, client, viewer_token):
        detail = _mock_priority("rec_001")
        detail["price_history"] = [{"tanggal": "2026-07-01", "harga": 80000}]
        detail["review"] = None
        with patch("src.api.mvp_routes.get_priority_detail", return_value=detail):
            resp = client.get("/api/mvp/priorities/rec_001", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            assert resp.json()["recommendation_id"] == "rec_001"

    @pytest.mark.integration
    def test_detail_404(self, client, viewer_token):
        with patch("src.api.mvp_routes.get_priority_detail", return_value=None):
            resp = client.get("/api/mvp/priorities/rec_nonexistent",
                              headers=_auth_headers(viewer_token))
            assert resp.status_code == 404

    @pytest.mark.integration
    def test_detail_requires_auth(self, client):
        assert client.get("/api/mvp/priorities/rec_001").status_code == 401


# ── Search tests ───────────────────────────────────────────────────────────

class TestMVPSearch:
    @pytest.mark.integration
    def test_search_results(self, client, viewer_token):
        # search_priorities imported locally inside api_search → patch at source
        with patch("src.application.mvp_orchestrator.search_priorities",
                   return_value={"results": [{"recommendation_id": "rec_001", "commodity": "Bawang Merah",
                                              "region": "Nasional", "risk_level": "kritis",
                                              "display_priority_score": 92.5, "relevance_score": 15,
                                              "matched_terms": ["bawang"]}],
                                 "total": 1, "query": "bawang", "offset": 0}):
            resp = client.get("/api/mvp/search?q=bawang", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    @pytest.mark.integration
    def test_search_empty_query_422(self, client, viewer_token):
        resp = client.get("/api/mvp/search", headers=_auth_headers(viewer_token))
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_search_requires_auth(self, client):
        assert client.get("/api/mvp/search?q=test").status_code == 401


# ── Export tests ───────────────────────────────────────────────────────────

class TestMVPExport:
    @pytest.mark.integration
    def test_export_csv(self, client, viewer_token):
        # export_priorities_file imported locally → patch at source
        with patch("src.application.mvp_orchestrator.export_priorities_file",
                   return_value=(b"\xef\xbb\xbfheader\nrow\n", "text/csv; charset=utf-8", "test.csv")):
            resp = client.get("/api/mvp/priorities/export?format=csv",
                              headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            assert "attachment" in resp.headers["content-disposition"]

    @pytest.mark.integration
    def test_export_xlsx(self, client, viewer_token):
        with patch("src.application.mvp_orchestrator.export_priorities_file",
                   return_value=(b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "t.xlsx")):
            resp = client.get("/api/mvp/priorities/export?format=xlsx",
                              headers=_auth_headers(viewer_token))
            assert resp.status_code == 200

    @pytest.mark.integration
    def test_export_invalid_format_422(self, client, viewer_token):
        resp = client.get("/api/mvp/priorities/export?format=pdf",
                          headers=_auth_headers(viewer_token))
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_export_single(self, client, viewer_token):
        with patch("src.application.mvp_orchestrator.export_priorities_file",
                   return_value=(b"csv", "text/csv; charset=utf-8", "detail.csv")):
            resp = client.get("/api/mvp/priorities/rec_001/export?format=csv",
                              headers=_auth_headers(viewer_token))
            assert resp.status_code == 200

    @pytest.mark.integration
    def test_export_requires_auth(self, client):
        assert client.get("/api/mvp/priorities/export?format=csv").status_code == 401


# ── Review tests ───────────────────────────────────────────────────────────

class TestMVPReview:
    @pytest.mark.integration
    def test_review_viewer_blocked(self, client, viewer_token):
        resp = client.post("/api/mvp/priorities/rec_001/review",
                           json={"status": "Untuk Dibahas", "note": "Test"},
                           headers=_auth_headers(viewer_token))
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_review_analyst_allowed(self, client, analyst_token):
        # get_priority_detail imported at module level → patch in mvp_routes
        # save_review imported locally → patch at source
        with patch("src.api.mvp_routes.get_priority_detail", return_value=_mock_priority("rec_001")), \
             patch("src.infrastructure.postgres.review_repository.save_review",
                   return_value={"id": 1, "status": "Untuk Dibahas", "note": "Test"}):
            resp = client.post("/api/mvp/priorities/rec_001/review",
                               json={"status": "Untuk Dibahas", "note": "Perlu rapat TPID"},
                               headers=_auth_headers(analyst_token))
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.integration
    def test_review_invalid_status_422(self, client, analyst_token):
        resp = client.post("/api/mvp/priorities/rec_001/review",
                           json={"status": "APPROVED", "note": "Bad"},
                           headers=_auth_headers(analyst_token))
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_review_note_too_long_422(self, client, analyst_token):
        resp = client.post("/api/mvp/priorities/rec_001/review",
                           json={"status": "Untuk Dibahas", "note": "x" * 2001},
                           headers=_auth_headers(analyst_token))
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_review_unknown_priority_404(self, client, analyst_token):
        with patch("src.api.mvp_routes.get_priority_detail", return_value=None):
            resp = client.post("/api/mvp/priorities/rec_nonexistent/review",
                               json={"status": "Untuk Dibahas"},
                               headers=_auth_headers(analyst_token))
            assert resp.status_code == 404

    @pytest.mark.integration
    def test_review_requires_auth(self, client):
        resp = client.post("/api/mvp/priorities/rec_001/review",
                           json={"status": "Untuk Dibahas"})
        assert resp.status_code == 401


# ── Transparency & service status tests ─────────────────────────────────────

class TestMVPTransparency:
    @pytest.mark.integration
    def test_transparency_shape(self, client, viewer_token):
        with patch("src.api.mvp_routes.get_transparency",
                   return_value={"data_sources": [], "model": {}, "priority_config": {}, "known_limitations": []}):
            resp = client.get("/api/mvp/transparency", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            for k in ("data_sources", "priority_config"):
                assert k in resp.json()

    @pytest.mark.integration
    def test_transparency_requires_auth(self, client):
        assert client.get("/api/mvp/transparency").status_code == 401


class TestMVPServiceStatus:
    @pytest.mark.integration
    def test_status_shape(self, client, viewer_token):
        with patch("src.api.mvp_routes.get_service_status",
                   return_value={"status": "ok", "database": {"connected": True, "type": "PostgreSQL"},
                                 "data_freshness": {"latest_data": "2026-07-13", "age_days": 0.0, "is_stale": False},
                                 "ml_service": {"online": False, "url": "http://localhost:8001"},
                                 "timestamp": "2026-07-13T12:00:00"}):
            resp = client.get("/api/mvp/service-status", headers=_auth_headers(viewer_token))
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.integration
    def test_status_requires_auth(self, client):
        assert client.get("/api/mvp/service-status").status_code == 401

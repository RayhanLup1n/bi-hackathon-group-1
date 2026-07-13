"""
MVP API Routes — decision-support workflow endpoints.

These endpoints serve the revamped Executive Dashboard, Priority Queue,
and Human Review workflow. They delegate to the application orchestration
layer (src/application/mvp_orchestrator.py) for all business logic.

Endpoints:
  GET  /api/mvp/overview                        — executive dashboard contract
  GET  /api/mvp/priorities                       — ranked priority list
  GET  /api/mvp/priorities/{recommendation_id}   — detail satu prioritas
  POST /api/mvp/priorities/{recommendation_id}/review — simpan human review
  GET  /api/mvp/transparency                     — data & model transparency
  GET  /api/mvp/service-status                    — aggregate health check

RBAC:
  - Viewer: read-only (GET endpoints)
  - Analyst: GET + POST review
  - Admin: all access
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import _current_user
from src.application.mvp_orchestrator import (
    get_overview,
    get_priorities,
    get_priority_detail,
    get_service_status,
    get_transparency,
)

logger = logging.getLogger(__name__)

mvp_router = APIRouter(prefix="/api/mvp", tags=["MVP Decision Workflow"])


# ── RBAC helpers ────────────────────────────────────────────────────────────

def _require_analyst(user: dict = Depends(_current_user)) -> dict:
    """Allow access only to analysts and admins."""
    if not user.get("is_analyst", False) and not user.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya analyst atau admin",
        )
    return user


def _require_admin(user: dict = Depends(_current_user)) -> dict:
    """Allow access only to admins."""
    if not user.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin",
        )
    return user


# ── Request model for review ────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    status: str = Field(
        ...,
        pattern=r"^(Belum Ditinjau|Untuk Dibahas|Ditunda|Ditolak)$",
        description="Review status",
    )
    note: str | None = Field(
        default=None,
        max_length=2000,
        description="Alasan atau catatan reviewer (maks 2000 karakter)",
    )


# ── Endpoints ───────────────────────────────────────────────────────────────

@mvp_router.get("/overview", summary="Executive Dashboard overview")
def api_overview(
    sim_date: Optional[date] = Query(
        default=None,
        description="Simulasi tanggal (YYYY-MM-DD)",
    ),
    user: dict = Depends(_current_user),
) -> dict:
    """Return aggregated data for the Executive Dashboard.

    Includes region status, data freshness, risk counts, top 3 priorities,
    review bundles, and latest human reviews.
    """
    try:
        return get_overview(sim_date=sim_date)
    except Exception as exc:
        logger.error("Overview failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memuat dashboard overview. Silakan coba beberapa saat lagi.",
        )


@mvp_router.get("/priorities", summary="Ranked priority list")
def api_priorities(
    sim_date: Optional[date] = Query(default=None),
    province: Optional[str] = Query(
        default=None,
        description="Filter provinsi (contoh: 'Jawa Barat')",
    ),
    risk: Optional[str] = Query(
        default=None,
        pattern=r"^(rendah|sedang|tinggi|kritis)$",
        description="Filter level risiko",
    ),
    user: dict = Depends(_current_user),
) -> list[dict]:
    """Return ranked list of all commodity priorities.

    Results are sorted by display_priority_score descending.
    Optional filters: province, risk level.
    """
    try:
        return get_priorities(
            sim_date=sim_date,
            province_filter=province,
            risk_filter=risk,
        )
    except Exception as exc:
        logger.error("Priorities failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memuat daftar prioritas.",
        )


@mvp_router.get(
    "/priorities/{recommendation_id}",
    summary="Detail satu prioritas",
)
def api_priority_detail(
    recommendation_id: str,
    sim_date: Optional[date] = Query(default=None),
    user: dict = Depends(_current_user),
) -> dict:
    """Return full detail for a single recommendation.

    Includes observed facts, model outputs, possible factors, missing
    information, response options, sources, price history, and review status.
    """
    try:
        detail = get_priority_detail(recommendation_id, sim_date=sim_date)
    except Exception as exc:
        logger.error("Priority detail failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memuat detail prioritas.",
        )

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prioritas dengan ID '{recommendation_id}' tidak ditemukan.",
        )

    return detail


@mvp_router.post(
    "/priorities/{recommendation_id}/review",
    summary="Simpan human review",
)
def api_submit_review(
    recommendation_id: str,
    body: ReviewRequest,
    sim_date: Optional[date] = Query(default=None),
    user: dict = Depends(_require_analyst),
) -> dict:
    """Save a human review for a recommendation.

    Analyst dapat memberi status:
      - Belum Ditinjau (default)
      - Untuk Dibahas
      - Ditunda
      - Ditolak

    Review disimpan dengan snapshot rekomendasi dan timestamp.
    """
    from src.infrastructure.postgres.review_repository import save_review

    # Get the current recommendation as snapshot
    detail = get_priority_detail(recommendation_id, sim_date=sim_date)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prioritas dengan ID '{recommendation_id}' tidak ditemukan.",
        )

    try:
        review = save_review(
            recommendation_id=recommendation_id,
            status=body.status,
            reviewer_user_id=user.get("id", 0),
            note=body.note,
            recommendation_snapshot=detail,
        )
        return {"status": "ok", "review": review}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Review save failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal menyimpan review.",
        )


@mvp_router.get("/transparency", summary="Data & model transparency")
def api_transparency(
    user: dict = Depends(_current_user),
) -> dict:
    """Return data sources, model metrics, weights, thresholds, and limitations.

    Semua konfigurasi yang mempengaruhi priority score dan response options
    ditampilkan di sini untuk audit dan transparansi.
    """
    try:
        return get_transparency()
    except Exception as exc:
        logger.error("Transparency failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memuat data transparansi.",
        )


@mvp_router.get("/service-status", summary="Aggregate service health")
def api_service_status(
    user: dict = Depends(_current_user),
) -> dict:
    """Return aggregate health: database, data freshness, ML service status.

    Public endpoint — tidak memerlukan role khusus.
    """
    try:
        return get_service_status()
    except Exception as exc:
        logger.error("Service status failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memeriksa status layanan.",
        )

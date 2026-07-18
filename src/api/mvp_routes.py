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
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.auth_routes import _current_user
from src.api.errors import AppError, ServiceUnavailableError
from src.application.mvp_orchestrator import (
    get_overview,
    get_priorities,
    get_priority_detail,
    get_service_status,
    get_sparklines,
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
    except AppError:
        raise  # let global handler convert
    except Exception as exc:
        logger.exception("Unexpected error in overview: %s", exc)
        raise ServiceUnavailableError(
            "Gagal memuat dashboard overview. Silakan coba beberapa saat lagi.",
            internal_message=str(exc),
        ) from exc


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
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in priorities")
        raise ServiceUnavailableError(
            "Gagal memuat daftar prioritas.",
            internal_message=str(exc),
        )


@mvp_router.get("/priorities/export", summary="Export seluruh prioritas (CSV/Excel)")
def api_export_priorities(
    fmt: str = Query(
        ...,
        alias="format",
        pattern=r"^(csv|xlsx)$",
        description="Format export: csv atau xlsx",
    ),
    sim_date: Optional[date] = Query(default=None),
    user: dict = Depends(_current_user),
) -> Response:
    """Download seluruh prioritas dalam format CSV atau Excel."""
    from src.application.mvp_orchestrator import export_priorities_file

    try:
        content, media_type, filename = export_priorities_file(
            fmt=fmt,
            sim_date=sim_date,
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in export priorities")
        raise ServiceUnavailableError(
            "Gagal mengekspor data prioritas.",
            internal_message=str(exc),
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
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in priority detail")
        raise ServiceUnavailableError(
            "Gagal memuat detail prioritas.",
            internal_message=str(exc),
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
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in review save")
        raise ServiceUnavailableError(
            "Gagal menyimpan review.",
            internal_message=str(exc),
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
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in transparency")
        raise ServiceUnavailableError(
            "Gagal memuat data transparansi.",
            internal_message=str(exc),
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
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in service status")
        raise ServiceUnavailableError(
            "Gagal memeriksa status layanan.",
            internal_message=str(exc),
        )


# ── Search & Export endpoints ──────────────────────────────────────────────

@mvp_router.get("/search", summary="Keyword search rekomendasi")
def api_search(
    q: str = Query(..., min_length=1, description="Query pencarian"),
    sim_date: Optional[date] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(_current_user),
) -> dict:
    """Cari rekomendasi berdasarkan keyword di seluruh field.

    Mencakup: nama komoditas, wilayah, level risiko, evidence label/value,
    missing information, dan price condition.

    Hasil diurutkan berdasarkan relevance score (cocok kata kunci)
    lalu display priority score.
    """
    from src.application.mvp_orchestrator import search_priorities

    try:
        return search_priorities(
            query=q,
            sim_date=sim_date,
            max_results=20,
            offset=offset,
        )
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in search")
        raise ServiceUnavailableError(
            "Gagal melakukan pencarian.",
            internal_message=str(exc),
        )


@mvp_router.get(
    "/priorities/{recommendation_id}/export",
    summary="Export satu rekomendasi (CSV/Excel)",
)
def api_export_single(
    recommendation_id: str,
    fmt: str = Query(
        ...,
        alias="format",
        pattern=r"^(csv|xlsx)$",
        description="Format export: csv atau xlsx",
    ),
    sim_date: Optional[date] = Query(default=None),
    user: dict = Depends(_current_user),
) -> Response:
    """Download detail satu rekomendasi dalam format CSV atau Excel."""
    from src.application.mvp_orchestrator import export_priorities_file

    try:
        content, media_type, filename = export_priorities_file(
            fmt=fmt,
            recommendation_id=recommendation_id,
            sim_date=sim_date,
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in export single")
        raise ServiceUnavailableError(
            "Gagal mengekspor detail prioritas.",
            internal_message=str(exc),
        )


@mvp_router.get("/sparklines", summary="Sparkline price data for dashboard")
def api_sparklines(
    sim_date: Optional[date] = Query(default=None),
    n_days: int = Query(default=14, ge=7, le=30),
    user: dict = Depends(_current_user),
) -> dict:
    """Get compact 14-day price history for all commodity x province combos.

    Returns labels (shared date axis) and per-recommendation sparkline
    data suitable for lightweight inline charts on the dashboard.

    Single call replaces N+1 price-history queries for each priority card.
    """
    try:
        return get_sparklines(sim_date=sim_date, n_days=n_days)
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in sparklines")
        raise ServiceUnavailableError(
            "Gagal memuat data sparkline.",
            internal_message=str(exc),
        )

"""
Review repository — CRUD operations for app.decision_review table.

Provides persistence for human review workflow:
  - Save a review (create or update)
  - Get review by recommendation_id
  - Get latest reviews (for dashboard overview)

Uses the shared db_cursor() context manager from the database module.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from src.infrastructure.postgres.database import db_cursor

# Valid review statuses (matches CHECK constraint in migration)
VALID_STATUSES = {"Belum Ditinjau", "Untuk Dibahas", "Ditunda", "Ditolak"}


def save_review(
    recommendation_id: str,
    status: str,
    reviewer_user_id: int,
    note: str | None = None,
    recommendation_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new review or update an existing one (UPSERT).

    If a review already exists for this recommendation_id, update it.
    Otherwise, insert a new row.

    Args:
        recommendation_id: The recommendation being reviewed.
        status: One of 'Belum Ditinjau', 'Untuk Dibahas', 'Ditunda', 'Ditolak'.
        reviewer_user_id: ID of the user submitting the review.
        note: Optional analyst note/reason.
        recommendation_snapshot: JSON-serializable snapshot of the Recommendation
            object at review time.

    Returns:
        The saved review row as a dict.

    Raises:
        ValueError: If status is invalid.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid review status: {status!r}. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )

    snapshot_json = json.dumps(
        recommendation_snapshot or {},
        ensure_ascii=False,
        default=str,
    )

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO app.decision_review (
                recommendation_id, status, reviewer_user_id, note,
                recommendation_snapshot
            ) VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (recommendation_id) DO UPDATE SET
                status = EXCLUDED.status,
                reviewer_user_id = EXCLUDED.reviewer_user_id,
                note = EXCLUDED.note,
                recommendation_snapshot = EXCLUDED.recommendation_snapshot,
                updated_at = NOW()
            RETURNING id, recommendation_id, status, reviewer_user_id,
                      note, recommendation_snapshot, created_at, updated_at
        """, (
            recommendation_id,
            status,
            reviewer_user_id,
            note or "",
            snapshot_json,
        ))
        row = cur.fetchone()
        return dict(row)


def get_review(recommendation_id: str) -> dict[str, Any] | None:
    """Get the review for a specific recommendation, if any.

    Args:
        recommendation_id: The recommendation to look up.

    Returns:
        Review dict or None if no review exists.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, recommendation_id, status, reviewer_user_id,
                   note, recommendation_snapshot, created_at, updated_at
            FROM app.decision_review
            WHERE recommendation_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
        """, (recommendation_id,))
        row = cur.fetchone()

    if row is None:
        return None

    review = dict(row)
    # Convert timestamps to ISO strings for JSON serialization
    for ts_field in ("created_at", "updated_at"):
        if isinstance(review.get(ts_field), datetime):
            review[ts_field] = review[ts_field].isoformat()

    # Parse the snapshot JSONB back to dict
    if isinstance(review.get("recommendation_snapshot"), str):
        try:
            review["recommendation_snapshot"] = json.loads(review["recommendation_snapshot"])
        except (json.JSONDecodeError, TypeError):
            pass

    return review


def get_latest_reviews(limit: int = 10) -> list[dict[str, Any]]:
    """Get the most recent reviews for dashboard overview.

    Args:
        limit: Maximum number of reviews to return.

    Returns:
        List of review dicts, most recent first.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, recommendation_id, status, reviewer_user_id,
                   note, created_at, updated_at
            FROM app.decision_review
            ORDER BY updated_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

    reviews = []
    for row in rows:
        review = dict(row)
        for ts_field in ("created_at", "updated_at"):
            if isinstance(review.get(ts_field), datetime):
                review[ts_field] = review[ts_field].isoformat()
        reviews.append(review)
    return reviews


def get_review_status_counts() -> dict[str, int]:
    """Get count of reviews per status for dashboard summary.

    Returns:
        Dict mapping status name → count.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT status, COUNT(*) AS count
            FROM app.decision_review
            GROUP BY status
        """)
        rows = cur.fetchall()

    counts = {s: 0 for s in VALID_STATUSES}
    for row in rows:
        counts[row["status"]] = row["count"]
    return counts

-- Migration: 001_create_decision_review
-- Description: Create decision_review table for human review workflow
-- Schema: app (PostgreSQL Gold layer)
-- Run: psql <connection_string> -f migrations/001_create_decision_review.sql

CREATE TABLE IF NOT EXISTS app.decision_review (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Belum Ditinjau'
        CHECK (status IN ('Belum Ditinjau', 'Untuk Dibahas', 'Ditunda', 'Ditolak')),
    reviewer_user_id INTEGER NOT NULL,
    note TEXT,
    recommendation_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique index for upsert by recommendation_id (one review per recommendation)
CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_review_recommendation_unique
    ON app.decision_review(recommendation_id);

-- Index for filtering by status
CREATE INDEX IF NOT EXISTS idx_decision_review_status
    ON app.decision_review(status);

-- Index for getting latest reviews per user
CREATE INDEX IF NOT EXISTS idx_decision_review_reviewer
    ON app.decision_review(reviewer_user_id, created_at DESC);

-- Trigger: auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION app.update_decision_review_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_review_updated_at ON app.decision_review;
CREATE TRIGGER trg_decision_review_updated_at
    BEFORE UPDATE ON app.decision_review
    FOR EACH ROW
    EXECUTE FUNCTION app.update_decision_review_updated_at();

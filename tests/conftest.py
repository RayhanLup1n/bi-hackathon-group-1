"""
Shared test fixtures and configuration.

This conftest is loaded automatically by pytest.
It patches database-related imports globally so integration tests
using TestClient don't try to connect to a real database.
"""
from __future__ import annotations

import os

# Environment setup must happen BEFORE any app modules are imported
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "integration-test-secret-32-chars-long!!")
os.environ.setdefault("SUPABASE_PASSWORD", "test")
os.environ.setdefault("SUPABASE_HOST", "localhost")
os.environ.setdefault("SUPABASE_PORT", "5432")
os.environ.setdefault("SUPABASE_DB", "postgres")
os.environ.setdefault("SUPABASE_USER", "postgres")
os.environ.setdefault("ENABLE_DOCS", "false")

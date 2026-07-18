"""
Shared PostgreSQL connection pool for the application serving database.

Usage:
    from src.infrastructure.postgres.database import get_conn, release_conn

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ...")
        rows = cur.fetchall()
        cur.close()
    finally:
        release_conn(conn)

Atau dengan context manager:
    from src.infrastructure.postgres.database import db_cursor

    with db_cursor() as cur:
        cur.execute("SELECT ...")
        rows = cur.fetchall()
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_dsn() -> str:
    """Build a PostgreSQL DSN from provider-neutral environment variables."""
    settings = _get_db_settings()

    return (
        f"host={settings['host']} port={settings['port']} dbname={settings['name']} "
        f"user={settings['user']} password={settings['password']}"
        f" sslmode={settings['sslmode']} connect_timeout=5"
        f" options='-c statement_timeout={settings['statement_timeout_ms']}'"
    )


def _get_db_settings() -> dict[str, str]:
    """Read provider-neutral DB settings with legacy Supabase compatibility.

    DB_* variables are the canonical names for Neon, self-hosted PostgreSQL,
    and any future provider. Existing SUPABASE_* variables remain valid
    during migration so old environments keep working.
    """

    def _get(name: str, legacy_name: str, default: str) -> str:
        return os.getenv(name, os.getenv(legacy_name, default))

    return {
        "host": _get("DB_HOST", "SUPABASE_HOST", "localhost"),
        "port": _get("DB_PORT", "SUPABASE_PORT", "5432"),
        "name": _get("DB_NAME", "SUPABASE_DB", "postgres"),
        "user": _get("DB_USER", "SUPABASE_USER", "postgres"),
        "password": _get("DB_PASSWORD", "SUPABASE_PASSWORD", ""),
        "sslmode": os.getenv("DB_SSLMODE", "require"),
        "statement_timeout_ms": os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000"),
    }


def init_pool(min_conn: int = 2, max_conn: int = 20) -> None:
    """Initialize the thread-safe connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, _get_dsn())


def get_conn() -> psycopg2.extensions.connection:
    """Get a connection from the pool."""
    if _pool is None:
        init_pool()
    return _pool.getconn()


def release_conn(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


def close_pool() -> None:
    """Close all connections. Call at app shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def db_cursor(dict_cursor: bool = True):
    """
    Context manager: get cursor, auto-commit/rollback, auto-release.

    Args:
        dict_cursor: If True, return rows as dicts (RealDictCursor).
                     If False, return rows as tuples.

    Usage:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM app.users")
            rows = cur.fetchall()  # list of dicts
    """
    conn = get_conn()
    cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    cur = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        finally:
            release_conn(conn)

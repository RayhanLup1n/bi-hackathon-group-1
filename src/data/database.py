"""
Shared database connection pool ke Supabase PostgreSQL.

Usage:
    from src.data.database import get_conn, release_conn

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ...")
        rows = cur.fetchall()
        cur.close()
    finally:
        release_conn(conn)

Atau dengan context manager:
    from src.data.database import db_cursor

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
    """Build DSN from environment variables."""
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")

    return (
        f"host={host} port={port} dbname={db} user={user} password={password}"
        f" sslmode=require connect_timeout=5"
        f" options='-c statement_timeout=15000'"
    )


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
        cur.close()
        release_conn(conn)

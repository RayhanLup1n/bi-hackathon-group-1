"""
Auth data layer: user management via Supabase PostgreSQL.

Table: app.users (id SERIAL, username, password_hash, role, created_at)

Provides the same interface that auth_routes.py expects:
- create_user, get_user_by_username, list_users, update_user, delete_user, verify_password
"""
from __future__ import annotations

import bcrypt

from src.data.database import db_cursor


# ── Password hashing ─────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Seed default users ───────────────────────────────────────────────────────

def init_db_auth() -> None:
    """Seed default users if table is empty."""
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM app.users")
        count = cur.fetchone()["cnt"]

    if count == 0:
        _seed_defaults()


def _seed_defaults() -> None:
    """Insert default admin and analyst users."""
    defaults = [
        ("admin", "admin123", "admin"),
        ("analyst", "analyst123", "analyst"),
    ]
    for username, password, role in defaults:
        try:
            create_user(username, password, role)
        except ValueError:
            pass  # already exists


# ── CRUD operations ──────────────────────────────────────────────────────────

def create_user(username: str, password: str, role: str = "viewer") -> dict:
    """Create a new user. Raises ValueError if username exists."""
    password_hash = _hash_password(password)

    with db_cursor() as cur:
        # Check if exists
        cur.execute("SELECT id FROM app.users WHERE username = %s", [username])
        if cur.fetchone():
            raise ValueError(f"Username '{username}' sudah terdaftar")

        cur.execute("""
            INSERT INTO app.users (username, password_hash, role)
            VALUES (%s, %s, %s)
            RETURNING id, username, role, created_at
        """, [username, password_hash, role])
        row = cur.fetchone()

    return dict(row)


def get_user_by_username(username: str) -> dict | None:
    """Get user by username. Returns None if not found."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, password_hash, role, created_at
            FROM app.users
            WHERE username = %s
        """, [username])
        row = cur.fetchone()

    return dict(row) if row else None


def list_users() -> list[dict]:
    """List all users (without password_hash)."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, role, created_at
            FROM app.users
            ORDER BY id
        """)
        rows = cur.fetchall()

    return [dict(r) for r in rows]


def update_user(
    user_id: int,
    new_password: str | None = None,
    new_role: str | None = None,
) -> dict | None:
    """Update user password and/or role. Returns updated user or None."""
    updates = []
    params = []

    if new_password:
        updates.append("password_hash = %s")
        params.append(_hash_password(new_password))
    if new_role:
        updates.append("role = %s")
        params.append(new_role)

    if not updates:
        return get_user_by_id(user_id)

    params.append(user_id)
    set_clause = ", ".join(updates)

    with db_cursor() as cur:
        cur.execute(f"""
            UPDATE app.users
            SET {set_clause}
            WHERE id = %s
            RETURNING id, username, role, created_at
        """, params)
        row = cur.fetchone()

    return dict(row) if row else None


def delete_user(user_id: int) -> bool:
    """Delete user by ID. Returns True if deleted."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM app.users WHERE id = %s", [user_id])
        return cur.rowcount > 0


def get_user_by_id(user_id: int) -> dict | None:
    """Get user by ID."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, role, created_at
            FROM app.users
            WHERE id = %s
        """, [user_id])
        row = cur.fetchone()

    return dict(row) if row else None

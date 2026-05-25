"""
Auth data layer: user management via Supabase PostgreSQL.

Table: app.users (id SERIAL, username, password_hash, is_admin, is_analyst, is_active, created_at)

Boolean flags instead of role VARCHAR:
  is_admin   = can manage users + full access
  is_analyst = can run RCA + view detailed analysis
  is_active  = account enabled (FALSE = soft-deleted/disabled)
  (none set) = viewer / read-only access

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


def _compute_role(user: dict) -> str:
    """Derive human-readable role string from boolean flags.

    Used for backward compatibility in API responses and JWT tokens.
    """
    if user.get("is_admin"):
        return "admin"
    elif user.get("is_analyst"):
        return "analyst"
    return "viewer"


def _user_to_dict(row: dict) -> dict:
    """Convert DB row to API-friendly dict with computed 'role' field."""
    d = dict(row)
    # Remove password_hash from output if present
    d.pop("password_hash", None)
    # Add computed role for backward compat
    d["role"] = _compute_role(d)
    return d


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
        # (username, password, is_admin, is_analyst)
        ("admin",   "admin123",   True,  False),
        ("analyst", "analyst123", False, True),
    ]
    for username, password, is_admin, is_analyst in defaults:
        try:
            create_user(username, password, is_admin=is_admin, is_analyst=is_analyst)
        except ValueError:
            pass  # already exists


# ── CRUD operations ──────────────────────────────────────────────────────────

def create_user(
    username: str,
    password: str,
    is_admin: bool = False,
    is_analyst: bool = False,
    is_active: bool = True,
) -> dict:
    """Create a new user. Raises ValueError if username exists."""
    password_hash = _hash_password(password)

    import psycopg2.errors

    with db_cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO app.users (username, password_hash, is_admin, is_analyst, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, username, is_admin, is_analyst, is_active, created_at
            """, [username, password_hash, is_admin, is_analyst, is_active])
            row = cur.fetchone()
        except psycopg2.errors.UniqueViolation:
            raise ValueError(f"Username '{username}' sudah terdaftar")

    return _user_to_dict(row)


def get_user_by_username(username: str) -> dict | None:
    """Get user by username (includes password_hash for auth)."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, password_hash, is_admin, is_analyst, is_active, created_at
            FROM app.users
            WHERE username = %s
        """, [username])
        row = cur.fetchone()

    if not row:
        return None
    d = dict(row)
    d["role"] = _compute_role(d)  # add computed role but keep password_hash
    return d


def list_users() -> list[dict]:
    """List all users (without password_hash)."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, is_admin, is_analyst, is_active, created_at
            FROM app.users
            ORDER BY id
        """)
        rows = cur.fetchall()

    return [_user_to_dict(r) for r in rows]


def update_user(
    user_id: int,
    new_password: str | None = None,
    is_admin: bool | None = None,
    is_analyst: bool | None = None,
    is_active: bool | None = None,
) -> dict | None:
    """Update user fields using fixed-column UPDATE with COALESCE pattern.

    Only non-None values are updated. Uses parameterized query throughout
    (no f-string SQL construction).
    """
    # Hash password if provided (not empty string)
    password_hash = _hash_password(new_password) if new_password else None

    with db_cursor() as cur:
        cur.execute("""
            UPDATE app.users
            SET password_hash = COALESCE(%s, password_hash),
                is_admin = COALESCE(%s, is_admin),
                is_analyst = COALESCE(%s, is_analyst),
                is_active = COALESCE(%s, is_active)
            WHERE id = %s
            RETURNING id, username, is_admin, is_analyst, is_active, created_at
        """, (password_hash, is_admin, is_analyst, is_active, user_id))
        row = cur.fetchone()

    return _user_to_dict(row) if row else None


def delete_user(user_id: int) -> bool:
    """Delete user by ID. Returns True if deleted."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM app.users WHERE id = %s", [user_id])
        return cur.rowcount > 0


def get_user_by_id(user_id: int) -> dict | None:
    """Get user by ID (without password_hash)."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, username, is_admin, is_analyst, is_active, created_at
            FROM app.users
            WHERE id = %s
        """, [user_id])
        row = cur.fetchone()

    return _user_to_dict(row) if row else None

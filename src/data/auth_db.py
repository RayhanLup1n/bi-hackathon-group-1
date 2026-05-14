"""
src/data/auth_db.py
===================
Database autentikasi pengguna.

Database : data/auth.db  (SQLite, auto-created saat init_db_auth dipanggil)

Tabel
-----
users  — id, username, password_hash, role, created_at

Role
----
admin    — akses penuh + manajemen pengguna
analyst  — akses penuh RCA dashboard
viewer   — akses read-only

Fungsi publik
-------------
init_db_auth()                             → buat tabel & seed default users (idempoten)
get_user_by_username(username)             → dict user atau None
verify_password(plain, hashed)             → bool
list_users()                               → list semua users (tanpa password_hash)
create_user(username, password, role)      → dict user baru
update_user(user_id, password, role)       → dict user yang diupdate atau None
delete_user(user_id)                       → None
"""
import sqlite3
from pathlib import Path

import bcrypt

DB_PATH = Path(__file__).parent.parent.parent / "data" / "auth.db"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

_SEED_USERS = [
    ("admin",   "admin123",   "admin"),
    ("analyst", "analyst123", "analyst"),
]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_db_auth() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = _conn()
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL UNIQUE,
            password_hash TEXT   NOT NULL,
            role         TEXT    NOT NULL DEFAULT 'viewer',
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for username, password, role in _SEED_USERS:
        exists = con.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            con.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, _hash(password), role),
            )
    con.commit()
    con.close()


def get_user_by_username(username: str) -> dict | None:
    con = _conn()
    row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    con.close()
    return dict(row) if row else None


def verify_password(plain: str, hashed: str) -> bool:
    return _verify(plain, hashed)


def list_users() -> list[dict]:
    con = _conn()
    rows = con.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY id"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str) -> dict:
    con = _conn()
    try:
        con.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, _hash(password), role),
        )
        con.commit()
        row = con.execute(
            "SELECT id, username, role, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' sudah terdaftar")
    finally:
        con.close()


def update_user(
    user_id: int,
    password: str | None = None,
    role: str | None = None,
) -> dict | None:
    con = _conn()
    if password:
        con.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash(password), user_id),
        )
    if role:
        con.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    con.commit()
    row = con.execute(
        "SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    con.close()
    return dict(row) if row else None


def delete_user(user_id: int) -> None:
    con = _conn()
    con.execute("DELETE FROM users WHERE id = ?", (user_id,))
    con.commit()
    con.close()

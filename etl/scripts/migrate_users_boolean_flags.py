"""
Migration script: users table role VARCHAR → boolean flags.

Adds is_admin, is_analyst, is_active columns to app.users,
migrates existing data from role column, then drops the role column.

Safe to run multiple times (idempotent).

Usage:
    uv run python etl/scripts/migrate_users_boolean_flags.py
"""
from __future__ import annotations

import os
import sys

import psycopg2
from dotenv import load_dotenv


def _get_dsn() -> str:
    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")
    return f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"


def migrate():
    # Load env from .envs/.env
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".envs", ".env")
    load_dotenv(env_path)

    dsn = _get_dsn()
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Step 1: Check if role column exists (old schema)
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'app'
              AND table_name = 'users'
              AND column_name = 'role'
        """)
        has_role_col = cur.fetchone() is not None

        # Step 2: Check if boolean columns already exist
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'app'
              AND table_name = 'users'
              AND column_name = 'is_admin'
        """)
        has_bool_cols = cur.fetchone() is not None

        if has_bool_cols and not has_role_col:
            print("[OK] Migration already complete — boolean flags exist, role column removed.")
            return

        if has_bool_cols and has_role_col:
            # Boolean cols exist but role col still there — just drop role
            print("[INFO] Boolean columns exist, dropping old role column...")
            cur.execute("ALTER TABLE app.users DROP COLUMN role")
            conn.commit()
            print("[OK] role column dropped.")
            return

        if not has_role_col and not has_bool_cols:
            # Fresh table — just add boolean columns
            print("[INFO] Fresh table — adding boolean columns...")
            cur.execute("""
                ALTER TABLE app.users
                ADD COLUMN is_admin   BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN is_analyst BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN is_active  BOOLEAN NOT NULL DEFAULT TRUE
            """)
            conn.commit()
            print("[OK] Boolean columns added.")
            return

        # Main migration: has role col, no boolean cols yet
        print("[INFO] Starting migration: role VARCHAR -> boolean flags...")

        # Step 3: Add new boolean columns
        print("  Adding is_admin, is_analyst, is_active columns...")
        cur.execute("""
            ALTER TABLE app.users
            ADD COLUMN is_admin   BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN is_analyst BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN is_active  BOOLEAN NOT NULL DEFAULT TRUE
        """)

        # Step 4: Migrate data from role to booleans
        print("  Migrating existing role data...")
        cur.execute("UPDATE app.users SET is_admin = TRUE WHERE role = 'admin'")
        admin_count = cur.rowcount
        cur.execute("UPDATE app.users SET is_analyst = TRUE WHERE role = 'analyst'")
        analyst_count = cur.rowcount
        # All users are active by default (already set via DEFAULT TRUE)

        print(f"  Migrated: {admin_count} admin(s), {analyst_count} analyst(s)")

        # Step 5: Drop old role column
        print("  Dropping old role column...")
        cur.execute("ALTER TABLE app.users DROP COLUMN role")

        conn.commit()
        print("[OK] Migration complete!")

        # Verify
        cur.execute("SELECT id, username, is_admin, is_analyst, is_active FROM app.users ORDER BY id")
        rows = cur.fetchall()
        print(f"\n  Users ({len(rows)}):")
        for row in rows:
            uid, uname, is_admin, is_analyst, is_active = row
            role = "admin" if is_admin else ("analyst" if is_analyst else "viewer")
            status = "active" if is_active else "INACTIVE"
            print(f"    #{uid} {uname:15s} role={role:8s} status={status}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migrate()

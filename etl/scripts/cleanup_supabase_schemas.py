"""
Cleanup Supabase: drop raw, staging, marts schemas.

Data has been migrated to BigQuery — only app.* tables remain in Supabase.
This script drops the data warehouse schemas to free up storage.

Usage:
    uv run python etl/scripts/cleanup_supabase_schemas.py
"""
from __future__ import annotations

import os
import sys

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Load env vars
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".envs", ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    """Drop raw, staging, marts schemas from Supabase PostgreSQL."""
    import psycopg2

    host = os.getenv("SUPABASE_HOST", "localhost")
    port = os.getenv("SUPABASE_PORT", "5432")
    db = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres")
    password = os.getenv("SUPABASE_PASSWORD", "")

    dsn = f"host={host} port={port} dbname={db} user={user} password={password} sslmode=require"

    print("Connecting to Supabase PostgreSQL...")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False  # use transaction
    cur = conn.cursor()

    schemas_to_drop = ["raw", "staging", "marts"]

    # First, show what's going to be dropped
    for schema in schemas_to_drop:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
        """, (schema,))
        tables = [row[0] for row in cur.fetchall()]
        if tables:
            print(f"\n  Schema '{schema}' — tables to drop: {', '.join(tables)}")
        else:
            print(f"\n  Schema '{schema}' — no tables (or schema doesn't exist)")

    # Verify app.* tables are safe
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'app'
        ORDER BY table_name
    """)
    app_tables = [row[0] for row in cur.fetchall()]
    print(f"\n  Schema 'app' — KEEPING: {', '.join(app_tables)}")

    # Drop schemas
    print("\nDropping schemas...")
    for schema in schemas_to_drop:
        try:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            print(f"  [OK] Dropped schema '{schema}'")
        except Exception as e:
            print(f"  [FAIL] Failed to drop '{schema}': {e}")
            conn.rollback()
            return

    conn.commit()

    # Verify: check remaining schemas
    cur.execute("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast',
                                   'pgsodium', 'vault', 'extensions',
                                   'graphql', 'graphql_public',
                                   'realtime', 'storage', 'supabase_functions',
                                   'supabase_migrations', 'auth', 'pgsodium_masks',
                                   'net', 'pg_net', '_analytics', '_realtime', '_supavisor')
        ORDER BY schema_name
    """)
    remaining = [row[0] for row in cur.fetchall()]
    print(f"\nRemaining user schemas: {remaining}")

    # Check database size
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    size = cur.fetchone()[0]
    print(f"Database size after cleanup: {size}")

    cur.close()
    conn.close()
    print("\nDone! Supabase cleanup complete.")


if __name__ == "__main__":
    main()

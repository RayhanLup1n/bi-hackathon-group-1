from src.infrastructure.postgres.database import _get_db_settings


def test_provider_neutral_database_variables_override_legacy_supabase_variables(monkeypatch):
    monkeypatch.setenv("SUPABASE_HOST", "supabase.example.com")
    monkeypatch.setenv("SUPABASE_PASSWORD", "legacy-secret")
    monkeypatch.setenv("DB_HOST", "neon.example.com")
    monkeypatch.setenv("DB_PASSWORD", "neon-secret")

    settings = _get_db_settings()

    assert settings["host"] == "neon.example.com"
    assert settings["password"] == "neon-secret"


def test_database_settings_keep_safe_defaults_for_local_development(monkeypatch):
    for name in (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_SSLMODE",
        "DB_STATEMENT_TIMEOUT_MS",
        "SUPABASE_HOST",
        "SUPABASE_PORT",
        "SUPABASE_DB",
        "SUPABASE_USER",
        "SUPABASE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = _get_db_settings()

    assert settings == {
        "host": "localhost",
        "port": "5432",
        "name": "postgres",
        "user": "postgres",
        "password": "",
        "sslmode": "require",
        "statement_timeout_ms": "15000",
    }

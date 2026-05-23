"""
Konfigurasi pipeline menggunakan pydantic-settings.
Nilai dibaca dari environment variables / file .env.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PihpsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Source ──────────────────────────────────────────
    base_url: str = Field(
        default="https://www.bi.go.id/hargapangan",
        alias="PIHPS_BASE_URL",
    )
    request_delay: float = Field(
        default=2.0,
        alias="PIHPS_REQUEST_DELAY_SECONDS",
    )
    max_retries: int = Field(
        default=3,
        alias="PIHPS_MAX_RETRIES",
    )
    timeout: int = Field(
        default=30,
        alias="PIHPS_TIMEOUT_SECONDS",
    )

    # ── Supabase PostgreSQL ──────────────────────────────
    supabase_host: str = Field(
        default="localhost",
        alias="SUPABASE_HOST",
    )
    supabase_port: int = Field(
        default=5432,
        alias="SUPABASE_PORT",
    )
    supabase_db: str = Field(
        default="postgres",
        alias="SUPABASE_DB",
    )
    supabase_user: str = Field(
        default="postgres",
        alias="SUPABASE_USER",
    )
    supabase_password: str = Field(
        default="",
        alias="SUPABASE_PASSWORD",
    )

    # ── dbt ─────────────────────────────────────────────
    dbt_project_dir: str = Field(
        default="/app/project/etl/dbt_project",
        alias="DBT_PROJECT_DIR",
    )
    dbt_profiles_dir: str = Field(
        default="/app/project/etl/dbt_project",
        alias="DBT_PROFILES_DIR",
    )
    dbt_target: str = Field(
        default="prod",
        alias="DBT_TARGET",
    )


# Singleton — import dari mana saja
settings = PihpsSettings()

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

    # ── Storage ─────────────────────────────────────────
    duckdb_path: str = Field(
        default="/opt/airflow/data/pihps.duckdb",
        alias="DUCKDB_PATH",
    )

    # ── dbt ─────────────────────────────────────────────
    dbt_project_dir: str = Field(
        default="/opt/airflow/dbt_project",
        alias="DBT_PROJECT_DIR",
    )
    dbt_profiles_dir: str = Field(
        default="/opt/airflow/dbt_project",
        alias="DBT_PROFILES_DIR",
    )
    dbt_target: str = Field(
        default="prod",
        alias="DBT_TARGET",
    )


# Singleton — import dari mana saja
settings = PihpsSettings()

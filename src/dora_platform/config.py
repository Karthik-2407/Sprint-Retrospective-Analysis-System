"""Configuration management for DORA Platform.

All settings are read from environment variables via pydantic-settings.
This is the only place in the codebase where environment variables are read directly.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- core ---
    app_env: str = Field(default="dev", description="Environment: dev|test|staging|prod")
    app_version: str = Field(default="dev", description="Application version")
    log_level: str = Field(default="INFO", description="Logging level")
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+psycopg://dora:change-me@db:5432/dora"),
        description="PostgreSQL connection string",
    )

    # --- GitHub App ---
    github_app_id: str | None = Field(default=None, description="GitHub App ID")
    github_app_private_key_path: Path | None = Field(
        default=None, description="Path to GitHub App private key"
    )
    github_webhook_secret: str | None = Field(
        default=None, description="GitHub webhook secret for signature verification"
    )

    # --- GitLab ---
    gitlab_base_url: str = Field(
        default="https://gitlab.com", description="GitLab instance base URL"
    )
    gitlab_token: str | None = Field(default=None, description="GitLab access token")
    gitlab_webhook_token: str | None = Field(
        default=None, description="GitLab webhook secret token"
    )

    # --- metrics ---
    min_sample_size: int = Field(
        default=30, description="Minimum sample size for Spearman correlation [DECIDED]"
    )
    metric_window_days: int = Field(default=28, description="Default rolling window in days")
    reconcile_interval_minutes: int = Field(
        default=15, description="Reconciliation job interval in minutes"
    )

    # --- ops ---
    grafana_admin_password: str = Field(default="change-me", description="Grafana admin password")
    sentry_dsn: str | None = Field(default=None, description="Sentry DSN for error tracking")

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

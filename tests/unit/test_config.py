"""Unit tests for configuration management."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from dora_platform.config import Settings, get_settings


class TestSettings:
    """Test Settings class loading and validation."""

    def test_default_values(self, monkeypatch):
        """Test that default values are loaded correctly."""
        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith(
                (
                    "APP_",
                    "DATABASE_",
                    "POSTGRES_",
                    "GITHUB_",
                    "GITLAB_",
                    "MIN_",
                    "METRIC_",
                    "RECONCILE_",
                    "GRAFANA_",
                    "SENTRY_",
                    "LOG_",
                )
            ):
                monkeypatch.delenv(key, raising=False)

        settings = Settings()

        assert settings.app_env == "dev"
        assert settings.app_version == "dev"
        assert settings.log_level == "INFO"
        assert str(settings.database_url) == "postgresql+psycopg://dora:change-me@db:5432/dora"
        assert settings.min_sample_size == 30
        assert settings.metric_window_days == 28
        assert settings.reconcile_interval_minutes == 15
        assert settings.grafana_admin_password == "change-me"

    def test_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("APP_VERSION", "1.2.3")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/testdb")
        monkeypatch.setenv("MIN_SAMPLE_SIZE", "50")
        monkeypatch.setenv("METRIC_WINDOW_DAYS", "90")

        settings = Settings()

        assert settings.app_env == "prod"
        assert settings.app_version == "1.2.3"
        assert settings.log_level == "DEBUG"
        assert str(settings.database_url) == "postgresql+psycopg://user:pass@localhost:5432/testdb"
        assert settings.min_sample_size == 50
        assert settings.metric_window_days == 90

    def test_github_app_settings(self, monkeypatch):
        """Test GitHub App settings."""
        monkeypatch.setenv("GITHUB_APP_ID", "12345")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", "/secrets/key.pem")
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "webhook-secret")

        settings = Settings()

        assert settings.github_app_id == "12345"
        assert settings.github_app_private_key_path == Path("/secrets/key.pem")
        assert settings.github_webhook_secret == "webhook-secret"

    def test_gitlab_settings(self, monkeypatch):
        """Test GitLab settings."""
        monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.com")
        monkeypatch.setenv("GITLAB_TOKEN", "glpat-token")
        monkeypatch.setenv("GITLAB_WEBHOOK_TOKEN", "webhook-token")

        settings = Settings()

        assert settings.gitlab_base_url == "https://gitlab.example.com"
        assert settings.gitlab_token == "glpat-token"
        assert settings.gitlab_webhook_token == "webhook-token"

    def test_computed_properties(self, monkeypatch):
        """Test computed properties for environment detection."""
        monkeypatch.setenv("APP_ENV", "dev")
        assert Settings().is_dev is True
        assert Settings().is_test is False
        assert Settings().is_prod is False

        monkeypatch.setenv("APP_ENV", "test")
        assert Settings().is_dev is False
        assert Settings().is_test is True
        assert Settings().is_prod is False

        monkeypatch.setenv("APP_ENV", "prod")
        assert Settings().is_dev is False
        assert Settings().is_test is False
        assert Settings().is_prod is True

    def test_invalid_database_url(self, monkeypatch):
        """Test that invalid database URL raises validation error."""
        monkeypatch.setenv("DATABASE_URL", "not-a-valid-url")

        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_min_sample_size(self, monkeypatch):
        """Test that invalid min_sample_size raises validation error."""
        monkeypatch.setenv("MIN_SAMPLE_SIZE", "not-a-number")

        with pytest.raises(ValidationError):
            Settings()

    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2


class TestConfigIntegration:
    """Integration tests for config with environment variables."""

    def test_load_from_env_file(self, monkeypatch):
        """Test loading settings from environment variables (simulating .env file)."""
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.setenv("APP_VERSION", "2.0.0")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://staging:pass@db:5432/staging")
        monkeypatch.setenv("MIN_SAMPLE_SIZE", "40")
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.app_env == "staging"
        assert settings.app_version == "2.0.0"
        assert settings.log_level == "WARNING"
        assert settings.min_sample_size == 40

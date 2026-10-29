"""Unit test configuration and fixtures."""

import pytest

from dora_platform.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings cache before each test to ensure clean state."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_settings(monkeypatch):
    """Fixture to provide mock settings for unit tests."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_VERSION", "test-version")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("MIN_SAMPLE_SIZE", "30")
    monkeypatch.setenv("METRIC_WINDOW_DAYS", "28")
    monkeypatch.setenv("RECONCILE_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test")
    get_settings.cache_clear()
    return get_settings()

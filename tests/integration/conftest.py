"""Integration test configuration and fixtures.

Uses the Docker Compose PostgreSQL database for integration tests.
Migrations are applied via Docker Compose before running tests.
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from dora_platform.config import get_settings
from dora_platform.db import get_session_factory


@pytest.fixture(scope="session")
def database_url():
    """Get database URL from environment (Docker Compose)."""
    # Use the Docker Compose database - replace 'db' host with 'localhost' for host-based tests
    # Port 5433 on host maps to 5432 in container (to avoid conflict with host PostgreSQL)
    # Use dora_app (non-superuser) to test RLS enforcement
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://dora_app:change-me@localhost:5433/dora"
    )
    # If running tests on host (not in Docker), replace 'db' with 'localhost'
    if "@db:" in url:
        url = url.replace("@db:", "@localhost:")
    return url


@pytest.fixture(scope="session", autouse=True)
def setup_env(database_url):
    """Set up environment variables for tests."""
    os.environ["DATABASE_URL"] = database_url
    os.environ["APP_ENV"] = "test"
    # Use the actual database credentials from .env (the DB is already running with these)
    os.environ["POSTGRES_DB"] = "dora"
    os.environ["POSTGRES_USER"] = "dora_app"
    os.environ["POSTGRES_PASSWORD"] = "change-me"
    os.environ["MIN_SAMPLE_SIZE"] = "30"
    os.environ["METRIC_WINDOW_DAYS"] = "28"
    os.environ["RECONCILE_INTERVAL_MINUTES"] = "15"
    os.environ["GRAFANA_ADMIN_PASSWORD"] = "change-me"
    get_settings.cache_clear()
    # Reset engine to pick up new DATABASE_URL
    from dora_platform.db.engine import reset_engine

    reset_engine()
    yield
    get_settings.cache_clear()
    reset_engine()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator:
    """Provide a database session for tests with automatic rollback."""
    async with get_session_factory()() as session:
        # Begin a transaction for the test
        async with session.begin():
            # Create a savepoint for nested transactions (allows test to commit/rollback)
            async with session.begin_nested():
                yield session
            # The outer transaction will be rolled back at the end


@pytest.fixture
def caplog(caplog):
    """Allow caplog to work with structlog."""
    import logging

    caplog.set_level(logging.DEBUG)
    return caplog

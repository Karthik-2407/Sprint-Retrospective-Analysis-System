"""SQLAlchemy async database engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dora_platform.config import get_settings

# Global engine and session factory (initialized lazily)
_engine = None
_async_session_factory = None


def create_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine with appropriate pool settings."""
    settings = get_settings()
    if settings.is_test:
        # Use NullPool for tests to avoid connection pooling issues
        return create_async_engine(
            str(settings.database_url),
            poolclass=NullPool,
            echo=settings.log_level == "DEBUG",
        )

    # Production/development: use default pool with reasonable settings
    return create_async_engine(
        str(settings.database_url),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.log_level == "DEBUG",
    )


def get_engine() -> AsyncEngine:
    """Get or create the global engine instance."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the global session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _async_session_factory


def reset_engine() -> None:
    """Reset the global engine (for testing with different DATABASE_URL)."""
    global _engine, _async_session_factory
    if _engine is not None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't close in running loop, schedule it
                loop.create_task(_engine.dispose())
            else:
                loop.run_until_complete(_engine.dispose())
        except RuntimeError:
            pass
    _engine = None
    _async_session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency for database sessions."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_context() -> AsyncGenerator[AsyncSession]:
    """Context manager for manual session handling (e.g., in worker jobs)."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

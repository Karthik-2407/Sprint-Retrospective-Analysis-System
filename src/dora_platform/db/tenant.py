"""Tenant context management for Row-Level Security (RLS).

Provides session/transaction-scoped tenant context for RLS enforcement.
"""

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Context variable to hold current tenant_id for the request/job
_current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> uuid.UUID | None:
    """Get the current tenant ID from context."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: uuid.UUID | None) -> None:
    """Set the current tenant ID in context."""
    _current_tenant_id.set(tenant_id)


@contextmanager
def tenant_context(tenant_id: uuid.UUID | None) -> Generator[None]:
    """Context manager to temporarily set tenant context."""
    token = _current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """
    Set tenant context for RLS on the database session.

    Executes SET LOCAL app.tenant_id which is scoped to the current transaction.
    This enables Row-Level Security policies to filter rows by tenant_id.

    Args:
        session: The async database session
        tenant_id: The tenant UUID, or None to clear context (uses zero UUID for RLS)
    """
    if tenant_id is not None:
        # Use string interpolation for SET LOCAL (doesn't support parameterized queries)
        await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        logger.debug("RLS tenant context set: %s", tenant_id)
    else:
        # Use a zero UUID to ensure no rows match when no tenant is set
        await session.execute(
            text("SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000000'")
        )
        logger.debug("RLS tenant context cleared")


async def get_tenant_context(session: AsyncSession) -> uuid.UUID | None:
    """
    Get the current tenant context from the database session.

    Returns:
        The tenant UUID if set, None otherwise
    """
    result = await session.execute(text("SHOW app.tenant_id"))
    value = result.scalar()
    if value and value != "00000000-0000-0000-0000-000000000000":
        return uuid.UUID(value)
    return None

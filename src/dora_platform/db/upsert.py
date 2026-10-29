"""Idempotent upsert helpers for provider-sourced data."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from dora_platform.db.models import (
        Commit,
        Deployment,
        Incident,
        ProviderConnection,
        PullRequest,
    )


async def upsert_provider_row[ModelT: DeclarativeBase](
    session: AsyncSession,
    model: type[ModelT],
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
    values: dict[str, Any],
) -> ModelT:
    """
    Upsert a provider-sourced row, returning the persisted instance.

    Uses the unique constraint on (tenant_id, provider, external_id) for conflict detection.

    Args:
        session: The async database session
        model: The SQLAlchemy model class
        tenant_id: The tenant UUID
        provider: The provider name (github, gitlab)
        external_id: The provider-specific external ID
        values: Dictionary of column values to upsert (excluding tenant_id, provider, external_id)

    Returns:
        The persisted model instance
    """
    # Build the insert statement with all values
    insert_values = {
        "tenant_id": tenant_id,
        "provider": provider,
        "external_id": external_id,
        **values,
    }

    stmt = (
        pg_insert(model)
        .values(insert_values)
        .on_conflict_do_update(
            index_elements=["tenant_id", "provider", "external_id"],
            set_=values,
        )
        .returning(model)
    )

    result = await session.execute(stmt)
    return result.scalar_one()


async def upsert_raw_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    event_type: str,
    delivery_id: str,
    payload_hash: str,
    payload: dict[str, Any],
) -> None:
    """
    Upsert a raw event (idempotent by delivery_id).

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        provider: The provider name
        event_type: The event type (e.g., pull_request, deployment)
        delivery_id: The provider's delivery ID (X-GitHub-Delivery, etc.)
        payload_hash: SHA-256 hash of the raw payload
        payload: The raw JSON payload
    """
    from dora_platform.db.models import RawEvent

    await upsert_provider_row(
        session=session,
        model=RawEvent,
        tenant_id=tenant_id,
        provider=provider,
        external_id=delivery_id,
        values={
            "event_type": event_type,
            "payload_hash": payload_hash,
            "payload": payload,
        },
    )


async def upsert_pull_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
    repository_id: uuid.UUID,
    values: dict[str, Any],
) -> "PullRequest":
    """
    Upsert a pull request.

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        provider: The provider name
        external_id: The PR/MR number
        repository_id: The repository UUID
        values: Dictionary of column values to upsert
    """
    from dora_platform.db.models import PullRequest

    values["repository_id"] = repository_id
    return await upsert_provider_row(
        session=session,
        model=PullRequest,
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
        values=values,
    )


async def upsert_deployment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
    repository_id: uuid.UUID,
    values: dict[str, Any],
) -> "Deployment":
    """
    Upsert a deployment.

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        provider: The provider name
        external_id: The deployment ID
        repository_id: The repository UUID
        values: Dictionary of column values to upsert
    """
    from dora_platform.db.models import Deployment

    values["repository_id"] = repository_id
    return await upsert_provider_row(
        session=session,
        model=Deployment,
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
        values=values,
    )


async def upsert_incident(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
    repository_id: uuid.UUID,
    values: dict[str, Any],
) -> "Incident":
    """
    Upsert an incident.

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        provider: The provider name
        external_id: The issue/incident number
        repository_id: The repository UUID
        values: Dictionary of column values to upsert
    """
    from dora_platform.db.models import Incident

    values["repository_id"] = repository_id
    return await upsert_provider_row(
        session=session,
        model=Incident,
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
        values=values,
    )


async def upsert_commit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    repository_id: uuid.UUID,
    sha: str,
    values: dict[str, Any],
) -> "Commit":
    """
    Upsert a commit (keyed by tenant_id, repository_id, sha).

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        repository_id: The repository UUID
        sha: The commit SHA
        values: Dictionary of column values to upsert
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from dora_platform.db.models import Commit

    insert_values = {
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "sha": sha,
        **values,
    }

    stmt = (
        pg_insert(Commit)
        .values(insert_values)
        .on_conflict_do_update(
            index_elements=["tenant_id", "repository_id", "sha"],
            set_=values,
        )
        .returning(Commit)
    )

    result = await session.execute(stmt)
    return result.scalar_one()


async def upsert_provider_connection(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
    project_id: uuid.UUID,
    values: dict[str, Any],
) -> "ProviderConnection":
    """
    Upsert a provider connection.

    Args:
        session: The async database session
        tenant_id: The tenant UUID
        provider: The provider name
        external_id: The installation/project/group ID
        project_id: The project UUID
        values: Dictionary of column values to upsert
    """
    from dora_platform.db.models import ProviderConnection

    values["project_id"] = project_id
    return await upsert_provider_row(
        session=session,
        model=ProviderConnection,
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
        values=values,
    )

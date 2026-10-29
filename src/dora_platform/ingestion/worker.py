"""Ingestion worker: processes raw_events through normalizers."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.config import settings
from dora_platform.db.engine import async_session_maker
from dora_platform.db.models import RawEvent, ProviderConnection
from dora_platform.ingestion.normalizers import get_normalizer_for_event
from dora_platform.observability.metrics import (
    EVENTS_NORMALIZED,
    NORMALIZATION_ERRORS,
    NORMALIZATION_LATENCY,
)
from dora_platform.observability.logging import get_logger

logger = get_logger(__name__)


async def process_raw_events_batch(batch_size: int = 100) -> int:
    """Process a batch of unprocessed raw events.

    Returns:
        Number of events processed
    """
    async with async_session_maker() as session:
        # Get unprocessed events
        stmt = (
            select(RawEvent)
            .where(RawEvent.processed_at.is_(None))
            .order_by(RawEvent.received_at)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            return 0

        processed = 0
        for event in events:
            try:
                await _process_single_event(session, event)
                processed += 1
            except Exception as e:
                logger.error("Failed to process event", event_id=event.id, error=str(e))
                NORMALIZATION_ERRORS.labels(provider=event.provider, error_type=type(e).__name__).inc()
                await _quarantine_event(session, event, str(e))

        await session.commit()
        return processed


async def _process_single_event(session: AsyncSession, event: RawEvent) -> None:
    """Process a single raw event through the normalizer."""
    import time

    start = time.perf_counter()

    # Parse payload
    payload = event.payload
    if isinstance(payload, str):
        payload = json.loads(payload)

    # Get normalizer
    normalizer = get_normalizer_for_event(event.provider, event.event_type)
    if not normalizer:
        logger.warning("No normalizer for event", provider=event.provider, event_type=event.event_type)
        event.processed_at = datetime.now(timezone.utc)
        event.error = f"No normalizer for {event.provider}/{event.event_type}"
        return

    # Create raw_event dict for normalizer
    raw_event_dict = {
        "event_type": event.event_type,
        "delivery_id": event.delivery_id,
        "payload": payload,
        "payload_hash": event.payload_hash,
    }

    # Normalize
    result = await normalizer.normalize(raw_event_dict)
    if not result:
        logger.warning("Normalizer returned None", provider=event.provider, event_type=event.event_type)
        event.processed_at = datetime.now(timezone.utc)
        event.error = "Normalizer returned no result"
        return

    # Upsert normalized entities
    await _upsert_normalized(session, result, event.tenant_id)

    # Mark processed
    event.processed_at = datetime.now(timezone.utc)
    event.error = None

    # Record metrics
    duration = time.perf_counter() - start
    NORMALIZATION_LATENCY.labels(provider=event.provider).observe(duration)
    EVENTS_NORMALIZED.labels(provider=event.provider, event_type=event.event_type).inc()

    logger.info(
        "Processed event",
        event_id=event.id,
        provider=event.provider,
        event_type=event.event_type,
        prs=len(result.pull_requests),
        deployments=len(result.deployments),
        incidents=len(result.incidents),
        commits=len(result.commits),
    )


async def _upsert_normalized(
    session: AsyncSession,
    result: "NormalizedResult",
    tenant_id: str,
) -> None:
    """Upsert normalized entities to database."""
    from dora_platform.db.upsert import (
        upsert_pull_request,
        upsert_deployment,
        upsert_incident,
        upsert_commit,
        upsert_repository,
    )

    # Upsert repositories first (needed for FK)
    repo_ids = set()
    for pr in result.pull_requests:
        repo_ids.add(pr["repository_external_id"])
    for dep in result.deployments:
        repo_ids.add(dep["repository_external_id"])
    for inc in result.incidents:
        repo_ids.add(inc["repository_external_id"])

    for repo_ext_id in repo_ids:
        provider, owner, name = _parse_repo_external_id(repo_ext_id)
        await upsert_repository(
            session,
            tenant_id=tenant_id,
            provider=provider,
            external_id=repo_ext_id,
            name=f"{owner}/{name}",
            owner=owner,
            url=f"https://github.com/{owner}/{name}" if provider == "github" else f"https://gitlab.com/{owner}/{name}",
        )

    # Upsert PRs
    for pr in result.pull_requests:
        await upsert_pull_request(session, tenant_id, pr)

    # Upsert deployments
    for dep in result.deployments:
        await upsert_deployment(session, tenant_id, dep)

    # Upsert incidents
    for inc in result.incidents:
        await upsert_incident(session, tenant_id, inc)

    # Upsert commits
    for commit in result.commits:
        await upsert_commit(session, tenant_id, commit)


def _parse_repo_external_id(external_id: str) -> tuple[str, str, str]:
    """Parse repository external_id into (provider, owner, name)."""
    # Format: "owner/name" for both GitHub and GitLab
    parts = external_id.split("/", 1)
    if len(parts) == 2:
        return ("github" if "github" in external_id.lower() else "gitlab", parts[0], parts[1])
    return ("github", "unknown", external_id)


async def _quarantine_event(session: AsyncSession, event: RawEvent, error: str) -> None:
    """Move failed event to quarantine."""
    from dora_platform.db.models import QuarantinedEvent

    quarantined = QuarantinedEvent(
        tenant_id=event.tenant_id,
        provider=event.provider,
        event_type=event.event_type,
        delivery_id=event.delivery_id,
        payload=event.payload,
        payload_hash=event.payload_hash,
        error=error,
        retry_count=event.retry_count + 1,
    )
    session.add(quarantined)
    event.processed_at = datetime.now(timezone.utc)
    event.error = error


async def process_all_pending() -> int:
    """Process all pending events (for testing/backfill)."""
    total = 0
    while True:
        processed = await process_raw_events_batch(100)
        total += processed
        if processed == 0:
            break
    return total
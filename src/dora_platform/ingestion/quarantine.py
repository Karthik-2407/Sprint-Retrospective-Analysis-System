"""Quarantine handling for failed normalizations."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.config import settings
from dora_platform.db.engine import async_session_maker
from dora_platform.db.models import QuarantinedEvent, RawEvent
from dora_platform.ingestion.normalizers import get_normalizer_for_event
from dora_platform.observability.metrics import QUARANTINE_RETRIES, QUARANTINE_SIZE
from dora_platform.observability.logging import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_HOURS = 24


async def retry_quarantined(max_events: int = 100) -> dict[str, int]:
    """Retry processing quarantined events that are eligible for retry.

    Returns:
        Stats dict with retried, succeeded, failed counts
    """
    stats = {"retried": 0, "succeeded": 0, "failed": 0}

    async with async_session_maker() as session:
        # Get events eligible for retry
        cutoff = datetime.now(timezone.utc) - timedelta(hours=RETRY_DELAY_HOURS)
        stmt = (
            select(QuarantinedEvent)
            .where(
                QuarantinedEvent.retry_count < MAX_RETRIES,
                QuarantinedEvent.last_retry_at < cutoff,
            )
            .order_by(QuarantinedEvent.last_retry_at)
            .limit(max_events)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        for event in events:
            stats["retried"] += 1
            try:
                await _retry_event(session, event)
                stats["succeeded"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error("Quarantine retry failed", event_id=event.id, error=str(e))
                await _increment_retry(session, event, str(e))

        await session.commit()

    QUARANTINE_RETRIES.inc(stats["retried"])
    return stats


async def _retry_event(session: AsyncSession, event: QuarantinedEvent) -> None:
    """Retry processing a single quarantined event."""
    # Parse payload
    import json

    payload = event.payload
    if isinstance(payload, str):
        payload = json.loads(payload)

    # Get normalizer
    normalizer = get_normalizer_for_event(event.provider, event.event_type)
    if not normalizer:
        raise ValueError(f"No normalizer for {event.provider}/{event.event_type}")

    # Normalize
    raw_event_dict = {
        "event_type": event.event_type,
        "delivery_id": event.delivery_id,
        "payload": payload,
        "payload_hash": event.payload_hash,
    }

    result = await normalizer.normalize(raw_event_dict)
    if not result:
        raise ValueError("Normalizer returned no result")

    # Upsert normalized entities
    await _upsert_normalized(session, result, event.tenant_id)

    # Delete from quarantine on success
    await session.delete(event)

    logger.info("Quarantine retry succeeded", event_id=event.id)


async def _increment_retry(session: AsyncSession, event: QuarantinedEvent, error: str) -> None:
    """Increment retry count and update error."""
    event.retry_count += 1
    event.last_retry_at = datetime.now(timezone.utc)
    event.error = error


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

    # Upsert repositories first
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

    for pr in result.pull_requests:
        await upsert_pull_request(session, tenant_id, pr)
    for dep in result.deployments:
        await upsert_deployment(session, tenant_id, dep)
    for inc in result.incidents:
        await upsert_incident(session, tenant_id, inc)
    for commit in result.commits:
        await upsert_commit(session, tenant_id, commit)


def _parse_repo_external_id(external_id: str) -> tuple[str, str, str]:
    parts = external_id.split("/", 1)
    if len(parts) == 2:
        return ("github" if "github" in external_id.lower() else "gitlab", parts[0], parts[1])
    return ("github", "unknown", external_id)


async def get_quarantine_stats() -> dict[str, Any]:
    """Get quarantine statistics."""
    async with async_session_maker() as session:
        stmt = select(QuarantinedEvent)
        result = await session.execute(stmt)
        events = result.scalars().all()

        by_provider = {}
        by_error = {}
        total = len(events)
        max_retries = 0

        for event in events:
            by_provider[event.provider] = by_provider.get(event.provider, 0) + 1
            if event.error:
                by_error[event.error[:100]] = by_error.get(event.error[:100], 0) + 1
            max_retries = max(max_retries, event.retry_count)

        QUARANTINE_SIZE.set(total)

        return {
            "total": total,
            "by_provider": by_provider,
            "by_error": by_error,
            "max_retries": max_retries,
        }


async def clear_quarantine(older_than_days: int = 30) -> int:
    """Clear old quarantined events.

    Args:
        older_than_days: Delete events older than this many days

    Returns:
        Number of events deleted
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    async with async_session_maker() as session:
        stmt = delete(QuarantinedEvent).where(QuarantinedEvent.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount
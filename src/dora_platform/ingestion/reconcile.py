"""Reconciliation: re-fetch recent events from provider APIs."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.config import settings
from dora_platform.db.engine import async_session_maker
from dora_platform.db.models import ProviderConnection, RawEvent
from dora_platform.providers import create_provider_client
from dora_platform.observability.metrics import RECONCILE_DURATION, RECONCILE_EVENTS_FETCHED
from dora_platform.observability.logging import get_logger

logger = get_logger(__name__)


async def reconcile_recent(
    hours: int = 24,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Reconcile recent events from all active provider connections.

    For each provider_connection:
    1. Get last_sync_at (or default to `hours` ago)
    2. Fetch events from provider API since that time
    3. Store in raw_events (idempotent on delivery_id)
    4. Update last_sync_at

    Args:
        hours: How far back to look if no last_sync_at
        batch_size: Max events to fetch per repo per call

    Returns:
        Dict with stats per provider connection
    """
    import time

    start = time.perf_counter()
    stats = {"total_fetched": 0, "total_stored": 0, "connections": []}

    async with async_session_maker() as session:
        # Get active provider connections
        stmt = select(ProviderConnection).where(ProviderConnection.is_active.is_(True))
        result = await session.execute(stmt)
        connections = result.scalars().all()

        for conn in connections:
            conn_stats = await _reconcile_connection(session, conn, hours, batch_size)
            stats["connections"].append(conn_stats)
            stats["total_fetched"] += conn_stats["fetched"]
            stats["total_stored"] += conn_stats["stored"]

        await session.commit()

    duration = time.perf_counter() - start
    RECONCILE_DURATION.observe(duration)
    RECONCILE_EVENTS_FETCHED.inc(stats["total_fetched"])

    logger.info("Reconciliation complete", **stats)
    return stats


async def _reconcile_connection(
    session: AsyncSession,
    conn: ProviderConnection,
    hours: int,
    batch_size: int,
) -> dict[str, Any]:
    """Reconcile a single provider connection."""
    provider = conn.provider
    config = conn.config or {}
    credentials = conn.credentials or {}

    # Merge credentials into config for auth
    full_config = {**config, **credentials}

    # Create provider client
    client = await create_provider_client(provider, full_config)

    try:
        # Determine since timestamp
        since = conn.last_sync_at
        if not since:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
        since_iso = since.isoformat().replace("+00:00", "Z")

        # Get repositories
        repos = await client.get_repositories()

        total_fetched = 0
        total_stored = 0

        for repo in repos:
            repo_ext_id = _get_repo_external_id(provider, repo)
            if not repo_ext_id:
                continue

            # Fetch and store PRs
            prs = await client.get_pull_requests(repo_ext_id, since=since_iso, per_page=batch_size)
            for pr in prs:
                stored = await _store_raw_event(session, conn.tenant_id, provider, repo_ext_id, "pull_request", pr)
                if stored:
                    total_stored += 1
                total_fetched += 1

            # Fetch and store deployments
            deps = await client.get_deployments(repo_ext_id, since=since_iso, per_page=batch_size)
            for dep in deps:
                stored = await _store_raw_event(session, conn.tenant_id, provider, repo_ext_id, "deployment", dep)
                if stored:
                    total_stored += 1
                total_fetched += 1

            # Fetch and store incidents
            incs = await client.get_incidents(repo_ext_id, since=since_iso, per_page=batch_size)
            for inc in incs:
                stored = await _store_raw_event(session, conn.tenant_id, provider, repo_ext_id, "issues", inc)
                if stored:
                    total_stored += 1
                total_fetched += 1

        # Update last_sync_at
        await session.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == conn.id)
            .values(last_sync_at=datetime.now(timezone.utc))
        )

        return {
            "connection_id": str(conn.id),
            "provider": provider,
            "fetched": total_fetched,
            "stored": total_stored,
        }

    finally:
        await client.close()


def _get_repo_external_id(provider: str, repo: dict[str, Any]) -> str | None:
    """Extract repository external_id from provider repo object."""
    if provider == "github":
        return f"{repo['owner']['login']}/{repo['name']}"
    elif provider == "gitlab":
        return f"{repo['namespace']['path']}/{repo['path']}"
    return None


async def _store_raw_event(
    session: AsyncSession,
    tenant_id: str,
    provider: str,
    repo_ext_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    """Store raw event idempotently. Returns True if newly stored."""
    import hashlib
    import json

    # Create delivery_id from provider-specific fields
    if provider == "github":
        delivery_id = f"github-{payload.get('id', '')}-{event_type}"
    else:
        delivery_id = f"gitlab-{payload.get('id', '')}-{event_type}"

    if not delivery_id or delivery_id.endswith("-"):
        return False

    # Compute payload hash for idempotency
    payload_json = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()

    # Check if already exists
    stmt = select(RawEvent).where(
        RawEvent.tenant_id == tenant_id,
        RawEvent.provider == provider,
        RawEvent.delivery_id == delivery_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return False

    # Insert new raw event
    raw_event = RawEvent(
        tenant_id=tenant_id,
        provider=provider,
        event_type=event_type,
        delivery_id=delivery_id,
        payload=payload,
        payload_hash=payload_hash,
        repository_external_id=repo_ext_id,
    )
    session.add(raw_event)
    return True
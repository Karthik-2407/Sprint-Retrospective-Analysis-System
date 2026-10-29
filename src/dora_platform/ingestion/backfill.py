"""Historical backfill with cursor-based pagination."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.db.engine import async_session_maker
from dora_platform.db.models import IngestionRun, ProviderConnection, RawEvent
from dora_platform.providers import create_provider_client
from dora_platform.observability.metrics import BACKFILL_DURATION, BACKFILL_EVENTS_PROCESSED
from dora_platform.observability.logging import get_logger

logger = get_logger(__name__)


async def backfill_historical(run_id: str) -> dict[str, Any]:
    """Execute a historical backfill ingestion run.

    Resumes from cursor, processes in batches, updates progress.

    Args:
        run_id: IngestionRun ID to execute

    Returns:
        Dict with final stats
    """
    import time

    start = time.perf_counter()

    async with async_session_maker() as session:
        # Get the ingestion run
        stmt = select(IngestionRun).where(IngestionRun.id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            raise ValueError(f"IngestionRun {run_id} not found")

        if run.status != "running":
            raise ValueError(f"IngestionRun {run_id} is not running (status: {run.status})")

        # Get provider connection
        stmt = select(ProviderConnection).where(ProviderConnection.id == run.provider_connection_id)
        result = await session.execute(stmt)
        conn = result.scalar_one_or_none()

        if not conn:
            raise ValueError(f"ProviderConnection {run.provider_connection_id} not found")

        # Parse cursor
        cursor = run.cursor or {}
        page = cursor.get("page", 1)
        since = cursor.get("since")
        repo_index = cursor.get("repo_index", 0)

        provider = conn.provider
        config = {**(conn.config or {}), **(conn.credentials or {})}

        client = await create_provider_client(provider, config)

        try:
            repos = await client.get_repositories()
            total_repos = len(repos)

            stats = {
                "total_fetched": 0,
                "total_stored": 0,
                "repos_processed": 0,
            }

            # Process repositories from cursor position
            for i in range(repo_index, total_repos):
                repo = repos[i]
                repo_ext_id = _get_repo_external_id(provider, repo)
                if not repo_ext_id:
                    continue

                # Process this repo
                repo_stats = await _backfill_repo(
                    session,
                    run,
                    client,
                    provider,
                    conn.tenant_id,
                    repo_ext_id,
                    since,
                    page,
                )

                stats["total_fetched"] += repo_stats["fetched"]
                stats["total_stored"] += repo_stats["stored"]

                # Update cursor after each repo
                cursor["repo_index"] = i + 1
                cursor["page"] = 1
                cursor["since"] = since
                run.cursor = cursor
                run.events_processed = stats["total_stored"]
                await session.commit()

                stats["repos_processed"] += 1

            # Mark run complete
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.events_processed = stats["total_stored"]
            await session.commit()

            duration = time.perf_counter() - start
            BACKFILL_DURATION.observe(duration)
            BACKFILL_EVENTS_PROCESSED.inc(stats["total_stored"])

            logger.info("Backfill complete", run_id=run_id, **stats)
            return stats

        finally:
            await client.close()


async def _backfill_repo(
    session: AsyncSession,
    run: IngestionRun,
    client: Any,
    provider: str,
    tenant_id: str,
    repo_ext_id: str,
    since: str | None,
    start_page: int,
) -> dict[str, int]:
    """Backfill a single repository."""
    stats = {"fetched": 0, "stored": 0}
    page = start_page
    per_page = 100

    while True:
        # Check if run was cancelled
        await session.refresh(run)
        if run.status == "cancelled":
            break

        # Fetch PRs
        prs = await client.get_pull_requests(repo_ext_id, since=since, per_page=per_page)
        if not prs and page > start_page:
            break

        for pr in prs:
            stored = await _store_raw_event(session, tenant_id, provider, repo_ext_id, "pull_request", pr)
            if stored:
                stats["stored"] += 1
            stats["fetched"] += 1

        # Fetch deployments
        deps = await client.get_deployments(repo_ext_id, since=since, per_page=per_page)
        for dep in deps:
            stored = await _store_raw_event(session, tenant_id, provider, repo_ext_id, "deployment", dep)
            if stored:
                stats["stored"] += 1
            stats["fetched"] += 1

        # Fetch incidents
        incs = await client.get_incidents(repo_ext_id, since=since, per_page=per_page)
        for inc in incs:
            stored = await _store_raw_event(session, tenant_id, provider, repo_ext_id, "issues", inc)
            if stored:
                stats["stored"] += 1
            stats["fetched"] += 1

        if len(prs) < per_page and len(deps) < per_page and len(incs) < per_page:
            break

        page += 1
        # Update cursor periodically
        if page % 10 == 0:
            run.cursor = {"page": page, "since": since, "repo_index": run.cursor.get("repo_index", 0)}
            await session.commit()

    return stats


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

    if provider == "github":
        delivery_id = f"github-{payload.get('id', '')}-{event_type}"
    else:
        delivery_id = f"gitlab-{payload.get('id', '')}-{event_type}"

    if not delivery_id or delivery_id.endswith("-"):
        return False

    payload_json = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()

    stmt = select(RawEvent).where(
        RawEvent.tenant_id == tenant_id,
        RawEvent.provider == provider,
        RawEvent.delivery_id == delivery_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return False

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


async def create_backfill_run(
    tenant_id: str,
    provider_connection_id: str,
    since: str | None = None,
) -> str:
    """Create a new backfill ingestion run.

    Returns:
        IngestionRun ID
    """
    from uuid import uuid4

    run = IngestionRun(
        id=uuid4(),
        tenant_id=tenant_id,
        provider_connection_id=provider_connection_id,
        run_type="backfill",
        status="running",
        cursor={"page": 1, "since": since, "repo_index": 0},
        events_processed=0,
    )

    async with async_session_maker() as session:
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return str(run.id)
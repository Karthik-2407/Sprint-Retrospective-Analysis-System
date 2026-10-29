"""Webhook endpoints for GitHub and GitLab."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.config import settings
from dora_platform.db.engine import async_session_maker
from dora_platform.db.models import ProviderConnection, RawEvent
from dora_platform.observability.metrics import (
    WEBHOOK_RECEIVED,
    WEBHOOK_PROCESSING_LATENCY,
)
from dora_platform.observability.logging import get_logger
from dora_platform.providers import get_webhook_verifier

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    """Receive GitHub webhook events."""
    import time

    start = time.perf_counter()

    # Read raw body
    body = await request.body()

    # Verify signature
    verifier = get_webhook_verifier("github")
    if not verifier.verify(body, x_hub_signature_256):
        logger.warning("Invalid GitHub webhook signature", delivery_id=x_github_delivery)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract installation_id to find provider_connection
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        logger.warning("No installation_id in GitHub webhook", event=x_github_event)
        raise HTTPException(status_code=400, detail="No installation_id")

    # Find matching provider_connection
    async with async_session_maker() as session:
        stmt = select(ProviderConnection).where(
            ProviderConnection.provider == "github",
            ProviderConnection.external_id == str(installation_id),
            ProviderConnection.is_active.is_(True),
        )
        result = await session.execute(stmt)
        conn = result.scalar_one_or_none()

        if not conn:
            logger.warning(
                "No active provider connection for installation",
                installation_id=installation_id,
            )
            raise HTTPException(status_code=404, detail="Provider connection not found")

        tenant_id = conn.tenant_id

        # Compute payload hash for idempotency
        payload_hash = hashlib.sha256(body).hexdigest()

        # Check if already processed (idempotent)
        stmt = select(RawEvent).where(
            RawEvent.tenant_id == tenant_id,
            RawEvent.provider == "github",
            RawEvent.delivery_id == x_github_delivery,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("Duplicate webhook ignored", delivery_id=x_github_delivery)
            return {"status": "duplicate"}

        # Store raw event
        raw_event = RawEvent(
            tenant_id=tenant_id,
            provider="github",
            event_type=x_github_event,
            delivery_id=x_github_delivery,
            payload=payload,
            payload_hash=payload_hash,
            repository_external_id=_extract_repo_id(payload),
        )
        session.add(raw_event)
        await session.commit()

    # Record metrics
    duration = time.perf_counter() - start
    WEBHOOK_PROCESSING_LATENCY.labels(provider="github").observe(duration)
    WEBHOOK_RECEIVED.labels(provider="github", event_type=x_github_event).inc()

    logger.info(
        "GitHub webhook received",
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        tenant_id=tenant_id,
    )

    return {"status": "accepted"}


@router.post("/gitlab", status_code=status.HTTP_202_ACCEPTED)
async def gitlab_webhook(
    request: Request,
    x_gitlab_event: str = Header(None, alias="X-Gitlab-Event"),
    x_gitlab_token: str = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event_uuid: str = Header(None, alias="X-Gitlab-Event-UUID"),
) -> dict[str, str]:
    """Receive GitLab webhook events."""
    import time

    start = time.perf_counter()

    # Read raw body
    body = await request.body()

    # Verify token
    verifier = get_webhook_verifier("gitlab")
    if not verifier.verify(body, x_gitlab_token):
        logger.warning("Invalid GitLab webhook token", event_uuid=x_gitlab_event_uuid)
        raise HTTPException(status_code=401, detail="Invalid token")

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract project_id to find provider_connection
    project_id = payload.get("project", {}).get("id")
    if not project_id:
        logger.warning("No project_id in GitLab webhook", event=x_gitlab_event)
        raise HTTPException(status_code=400, detail="No project_id")

    # Find matching provider_connection
    async with async_session_maker() as session:
        stmt = select(ProviderConnection).where(
            ProviderConnection.provider == "gitlab",
            ProviderConnection.external_id == str(project_id),
            ProviderConnection.is_active.is_(True),
        )
        result = await session.execute(stmt)
        conn = result.scalar_one_or_none()

        if not conn:
            logger.warning(
                "No active provider connection for project",
                project_id=project_id,
            )
            raise HTTPException(status_code=404, detail="Provider connection not found")

        tenant_id = conn.tenant_id

        # Use event UUID as delivery_id, or generate one
        delivery_id = x_gitlab_event_uuid or f"gitlab-{project_id}-{x_gitlab_event}-{int(time.time())}"

        # Compute payload hash for idempotency
        payload_hash = hashlib.sha256(body).hexdigest()

        # Check if already processed (idempotent)
        stmt = select(RawEvent).where(
            RawEvent.tenant_id == tenant_id,
            RawEvent.provider == "gitlab",
            RawEvent.delivery_id == delivery_id,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("Duplicate webhook ignored", delivery_id=delivery_id)
            return {"status": "duplicate"}

        # Store raw event
        raw_event = RawEvent(
            tenant_id=tenant_id,
            provider="gitlab",
            event_type=x_gitlab_event,
            delivery_id=delivery_id,
            payload=payload,
            payload_hash=payload_hash,
            repository_external_id=_extract_gitlab_repo_id(payload),
        )
        session.add(raw_event)
        await session.commit()

    # Record metrics
    duration = time.perf_counter() - start
    WEBHOOK_PROCESSING_LATENCY.labels(provider="gitlab").observe(duration)
    WEBHOOK_RECEIVED.labels(provider="gitlab", event_type=x_gitlab_event).inc()

    logger.info(
        "GitLab webhook received",
        event_type=x_gitlab_event,
        delivery_id=delivery_id,
        tenant_id=tenant_id,
    )

    return {"status": "accepted"}


def _extract_repo_id(payload: dict[str, Any]) -> str | None:
    """Extract repository external_id from GitHub webhook payload."""
    repo = payload.get("repository")
    if repo:
        return f"{repo['owner']['login']}/{repo['name']}"
    return None


def _extract_gitlab_repo_id(payload: dict[str, Any]) -> str | None:
    """Extract repository external_id from GitLab webhook payload."""
    project = payload.get("project")
    if project:
        return f"{project['namespace']['path']}/{project['path']}"
    return None
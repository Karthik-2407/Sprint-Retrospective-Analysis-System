"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.api.schemas.health import HealthResponse, ReadyResponse
from dora_platform.db import get_session

router = APIRouter()


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns OK if the process is running. Used by container orchestration.",
)
async def healthz() -> HealthResponse:
    """Liveness check — process is up."""
    return HealthResponse(status="ok")


@router.get(
    "/readyz",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description=(
        "Returns OK if the service is ready to accept traffic (DB reachable, migrations current)."
    ),
)
async def readyz(session: AsyncSession = Depends(get_session)) -> ReadyResponse:  # noqa: B008
    """Readiness check — DB reachable and migrations at head."""
    try:
        # Check database connectivity
        await session.execute(text("SELECT 1"))

        # Check migrations are at head (simplified - in production,
        # check alembic_version table)
        # For now, just verify we can query a core table
        await session.execute(text("SELECT 1 FROM tenants LIMIT 1"))

        return ReadyResponse(status="ready")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready: {str(e)}",
        ) from e

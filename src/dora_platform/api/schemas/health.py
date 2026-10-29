"""Health check response schemas."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness probe response."""

    model_config = ConfigDict(frozen=True)

    status: str = "ok"


class ReadyResponse(BaseModel):
    """Readiness probe response."""

    model_config = ConfigDict(frozen=True)

    status: str = "ready"

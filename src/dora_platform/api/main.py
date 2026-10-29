"""FastAPI application for DORA Platform."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from dora_platform.api.routers import health, webhooks
from dora_platform.config import settings
from dora_platform.db import get_engine
from dora_platform.observability.logging import configure_logging, get_logger
from dora_platform.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY

# Configure structured logging
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("starting_up", version=settings.app_version, env=settings.app_env)

    # Verify database connectivity
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database_connected")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("shutting_down")
    await get_engine().dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="DORA Metrics Analytics Platform",
        version=settings.app_version,
        description="API for computing and visualizing DORA software delivery metrics",
        docs_url="/docs" if settings.is_dev else None,
        redoc_url="/redoc" if settings.is_dev else None,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_dev else [],  # Configure properly for prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        import uuid

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Structured logging middleware
    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        import time

        start_time = time.perf_counter()

        # Extract tenant context if available (from auth in future phases)
        tenant_id = getattr(request.state, "tenant_id", None)

        response = await call_next(request)

        duration = time.perf_counter() - start_time

        # Record Prometheus metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)

        logger.info(
            "http_request",
            request_id=request.state.request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
            tenant_id=str(tenant_id) if tenant_id else None,
        )

        return response

    # Include routers
    # Root-level health endpoints for Docker healthchecks
    app.include_router(health.router, prefix="", tags=["health"])
    # API v1 routes
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])

    return app


app = create_app()

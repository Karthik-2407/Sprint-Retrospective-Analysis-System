"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from dora_platform.config import settings


def configure_logging() -> None:
    """Configure structlog for JSON output with context variables."""
    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def bind_request_context(request_id: str | None = None, tenant_id: str | None = None) -> None:
    """Bind request-scoped context variables."""
    if request_id:
        bind_contextvars(request_id=request_id)
    if tenant_id:
        bind_contextvars(tenant_id=tenant_id)


def clear_request_context() -> None:
    """Clear request-scoped context variables."""
    clear_contextvars()


def log_with_context(
    logger: structlog.stdlib.BoundLogger, level: str, event: str, **kwargs: Any
) -> None:
    """Log with current context variables."""
    getattr(logger, level)(event, **kwargs)

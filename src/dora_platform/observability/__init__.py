"""Observability package for DORA Platform."""

from dora_platform.observability.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    log_with_context,
)
from dora_platform.observability.metrics import (
    ERRORS,
    INGESTION_EVENTS,
    INGESTION_LAG,
    PROVIDER_RATE_LIMIT_REMAINING,
    QUEUE_DEPTH,
    RECONCILIATION_DURATION,
    RECONCILIATION_RUNS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    SNAPSHOT_RECOMPUTE_DURATION,
    SNAPSHOTS_COMPUTED,
    WEBHOOK_PROCESSING_LATENCY,
    WEBHOOK_RECEIVED,
)

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    "bind_request_context",
    "clear_request_context",
    "log_with_context",
    # Metrics
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "WEBHOOK_RECEIVED",
    "WEBHOOK_PROCESSING_LATENCY",
    "INGESTION_EVENTS",
    "INGESTION_LAG",
    "RECONCILIATION_RUNS",
    "RECONCILIATION_DURATION",
    "QUEUE_DEPTH",
    "PROVIDER_RATE_LIMIT_REMAINING",
    "SNAPSHOT_RECOMPUTE_DURATION",
    "SNAPSHOTS_COMPUTED",
    "ERRORS",
]

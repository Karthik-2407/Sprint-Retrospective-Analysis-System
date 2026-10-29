"""Prometheus metrics for operational observability."""

from prometheus_client import Counter, Gauge, Histogram

# HTTP request metrics
REQUEST_COUNT = Counter(
    "dora_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "dora_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Webhook metrics
WEBHOOK_RECEIVED = Counter(
    "dora_webhook_received_total",
    "Total webhooks received",
    ["provider", "event_type", "status"],  # status: verified, rejected, error
)

WEBHOOK_PROCESSING_LATENCY = Histogram(
    "dora_webhook_processing_duration_seconds",
    "Webhook processing latency in seconds",
    ["provider", "event_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Ingestion metrics
INGESTION_EVENTS = Counter(
    "dora_ingestion_events_total",
    "Total events ingested",
    ["provider", "event_type", "status"],  # status: success, duplicate, error
)

INGESTION_LAG = Gauge(
    "dora_ingestion_lag_seconds",
    "Time since last successful ingestion per provider",
    ["provider"],
)

# Normalization metrics
EVENTS_NORMALIZED = Counter(
    "dora_events_normalized_total",
    "Total events normalized",
    ["provider", "event_type"],
)

NORMALIZATION_LATENCY = Histogram(
    "dora_normalization_duration_seconds",
    "Event normalization latency in seconds",
    ["provider"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

NORMALIZATION_ERRORS = Counter(
    "dora_normalization_errors_total",
    "Total normalization errors",
    ["provider", "error_type"],
)

# Reconciliation metrics
RECONCILIATION_RUNS = Counter(
    "dora_reconciliation_runs_total",
    "Total reconciliation runs",
    ["status"],  # success, error
)

RECONCILIATION_DURATION = Histogram(
    "dora_reconciliation_duration_seconds",
    "Reconciliation run duration in seconds",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

RECONCILE_DURATION = Histogram(
    "dora_reconcile_duration_seconds",
    "Reconcile recent events duration in seconds",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

RECONCILE_EVENTS_FETCHED = Counter(
    "dora_reconcile_events_fetched_total",
    "Total events fetched during reconciliation",
)

# Backfill metrics
BACKFILL_DURATION = Histogram(
    "dora_backfill_duration_seconds",
    "Backfill run duration in seconds",
    buckets=(10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0),
)

BACKFILL_EVENTS_PROCESSED = Counter(
    "dora_backfill_events_processed_total",
    "Total events processed during backfill",
)

# Quarantine metrics
QUARANTINE_RETRIES = Counter(
    "dora_quarantine_retries_total",
    "Total quarantine retry attempts",
)

QUARANTINE_SIZE = Gauge(
    "dora_quarantine_size",
    "Current number of quarantined events",
)

# Queue metrics
QUEUE_DEPTH = Gauge(
    "dora_queue_depth",
    "Current queue depth for background jobs",
    ["queue_name"],
)

# Provider metrics
PROVIDER_RATE_LIMIT_REMAINING = Gauge(
    "dora_provider_rate_limit_remaining",
    "Remaining API rate limit for provider",
    ["provider"],
)

# Snapshot metrics
SNAPSHOT_RECOMPUTE_DURATION = Histogram(
    "dora_snapshot_recompute_duration_seconds",
    "Metric snapshot recomputation duration in seconds",
    ["metric"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

SNAPSHOTS_COMPUTED = Counter(
    "dora_snapshots_computed_total",
    "Total metric snapshots computed",
    ["metric", "status"],  # status: ok, no_events, undetectable, partial_data, insufficient_sample
)

# Error metrics
ERRORS = Counter(
    "dora_errors_total",
    "Total errors by type",
    ["component", "error_type"],
)

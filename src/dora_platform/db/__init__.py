"""Database layer for DORA Platform."""

from dora_platform.db.engine import (
    create_engine,
    get_engine,
    get_session,
    get_session_factory,
    reset_engine,
    session_context,
)
from dora_platform.db.models import (
    Base,
    Commit,
    Deployment,
    DeploymentCommit,
    Incident,
    IncidentDeploymentLink,
    IngestionRun,
    MetricSnapshot,
    PRCommit,
    Project,
    ProviderConnection,
    PullRequest,
    QuarantinedEvent,
    RawEvent,
    Repository,
    Tenant,
)
from dora_platform.db.tenant import (
    get_current_tenant_id,
    get_tenant_context,
    set_current_tenant_id,
    set_tenant_context,
    tenant_context,
)
from dora_platform.db.upsert import (
    upsert_commit,
    upsert_deployment,
    upsert_incident,
    upsert_provider_connection,
    upsert_provider_row,
    upsert_pull_request,
    upsert_raw_event,
)

__all__ = [
    # Engine & Session
    "get_engine",
    "get_session_factory",
    "reset_engine",
    "create_engine",
    "get_session",
    "session_context",
    # Models
    "Base",
    "Tenant",
    "Project",
    "Repository",
    "ProviderConnection",
    "RawEvent",
    "QuarantinedEvent",
    "PullRequest",
    "Commit",
    "PRCommit",
    "Deployment",
    "DeploymentCommit",
    "Incident",
    "IncidentDeploymentLink",
    "MetricSnapshot",
    "IngestionRun",
    # Tenant Context (RLS)
    "get_current_tenant_id",
    "set_current_tenant_id",
    "set_tenant_context",
    "get_tenant_context",
    "tenant_context",
    # Upsert Helpers
    "upsert_provider_row",
    "upsert_raw_event",
    "upsert_pull_request",
    "upsert_deployment",
    "upsert_incident",
    "upsert_commit",
    "upsert_provider_connection",
]

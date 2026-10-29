"""Provider-neutral domain models for metric computation.

These are pure dataclasses with no SQLAlchemy dependencies.
All timestamps are timezone-aware UTC datetimes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any


class PRState(StrEnum):
    """Pull request / merge request state."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class DeploymentStatus(StrEnum):
    """Deployment status."""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING = "pending"


class IncidentState(StrEnum):
    """Incident state."""

    OPEN = "open"
    CLOSED = "closed"
    RESOLVED = "resolved"


class IncidentSeverity(StrEnum):
    """Incident severity."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentSource(StrEnum):
    """Incident source type."""

    LABELED_ISSUE = "labeled_issue"
    NATIVE_INCIDENT = "native_incident"
    MANUAL = "manual"


class LinkRule(StrEnum):
    """Strict incident-to-deployment linking rules."""

    R1_EXPLICIT = "R1"  # Explicit deployment_id field
    R2_SHA_REF = "R2"  # References deployment SHA in body/comments
    R3_WINDOW = "R3"  # Opened within window after failed deployment (configurable)


@dataclass(frozen=True, slots=True)
class Commit:
    """Git commit."""

    sha: str
    repository_id: uuid.UUID
    author_name: str | None = None
    author_email: str | None = None
    authored_at: datetime | None = None
    message: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PullRequest:
    """Pull request / merge request."""

    id: uuid.UUID
    repository_id: uuid.UUID
    provider: str  # github | gitlab
    external_id: str  # PR/MR number
    title: str
    state: PRState
    merge_method: str | None = None  # merge, squash, rebase
    merge_commit_sha: str | None = None
    base_branch: str = ""
    head_branch: str = ""
    opened_at: datetime | None = None
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    commits: tuple[Commit, ...] = field(default_factory=tuple)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_merged(self) -> bool:
        return self.state == PRState.MERGED and self.merged_at is not None


@dataclass(frozen=True, slots=True)
class Deployment:
    """Deployment."""

    id: uuid.UUID
    repository_id: uuid.UUID
    provider: str  # github | gitlab
    external_id: str  # deployment ID
    environment: str  # production, staging, etc.
    sha: str  # deployed commit SHA
    status: DeploymentStatus
    ref: str | None = None  # branch/tag ref
    deployed_at: datetime | None = None
    finished_at: datetime | None = None
    commits: tuple[Commit, ...] = field(default_factory=tuple)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_successful(self) -> bool:
        return self.status == DeploymentStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status == DeploymentStatus.FAILED


@dataclass(frozen=True, slots=True)
class Incident:
    """Incident / issue representing a production failure."""

    id: uuid.UUID
    repository_id: uuid.UUID
    provider: str  # github | gitlab | manual
    external_id: str  # issue/incident number
    title: str
    state: IncidentState
    severity: IncidentSeverity | None = None
    source: IncidentSource = IncidentSource.LABELED_ISSUE
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    deployment_id: uuid.UUID | None = None  # R1: explicit link
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_resolved(self) -> bool:
        return self.state == IncidentState.RESOLVED and self.resolved_at is not None


@dataclass(frozen=True, slots=True)
class IncidentDeploymentLink:
    """Explicit, auditable link between an incident and a deployment."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    incident_id: uuid.UUID
    deployment_id: uuid.UUID
    rule_id: LinkRule
    evidence: dict[str, Any]  # JSONB: what matched (field, pattern, matched_text, etc.)
    created_by: str  # system | manual
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Window:
    """Time window for metric computation."""

    window_type: str  # rolling_28d, rolling_90d, calendar_week, calendar_month
    start: datetime
    end: datetime


# Conversion functions from DB models to domain models
# These avoid circular imports by using TYPE_CHECKING

if TYPE_CHECKING:
    from dora_platform.db.models import (
        Commit as DBCommit,
    )
    from dora_platform.db.models import (
        Deployment as DBDeployment,
    )
    from dora_platform.db.models import (
        Incident as DBIncident,
    )
    from dora_platform.db.models import (
        IncidentDeploymentLink as DBIncidentDeploymentLink,
    )
    from dora_platform.db.models import (
        PullRequest as DBPullRequest,
    )


def commit_from_db(db_commit: "DBCommit") -> Commit:
    """Convert DB Commit to domain Commit."""
    return Commit(
        sha=db_commit.sha,
        repository_id=db_commit.repository_id,
        author_name=db_commit.author_name,
        author_email=db_commit.author_email,
        authored_at=db_commit.authored_at,
        message=db_commit.message,
        raw_data={},
    )


def commit_to_db_kwargs(domain_commit: Commit) -> dict[str, Any]:
    """Convert domain Commit to DB kwargs."""
    return {
        "sha": domain_commit.sha,
        "repository_id": domain_commit.repository_id,
        "author_name": domain_commit.author_name,
        "author_email": domain_commit.author_email,
        "authored_at": domain_commit.authored_at,
        "committed_at": domain_commit.authored_at,  # Use authored_at as fallback
        "message": domain_commit.message or "",
    }


def pull_request_from_db(db_pr: "DBPullRequest") -> PullRequest:
    """Convert DB PullRequest to domain PullRequest."""
    return PullRequest(
        id=db_pr.id,
        repository_id=db_pr.repository_id,
        provider=db_pr.provider,
        external_id=db_pr.external_id,
        title=db_pr.title,
        state=PRState(db_pr.state),
        merge_method=db_pr.merge_method,
        merge_commit_sha=db_pr.merge_commit_sha,
        base_branch=db_pr.base_branch or "",
        head_branch=db_pr.head_branch or "",
        opened_at=db_pr.opened_at,
        merged_at=db_pr.merged_at,
        closed_at=db_pr.closed_at,
        commits=tuple(commit_from_db(c) for c in db_pr.commits),
        raw_data=db_pr.raw_data or {},
    )


def deployment_from_db(db_deployment: "DBDeployment") -> Deployment:
    """Convert DB Deployment to domain Deployment."""
    return Deployment(
        id=db_deployment.id,
        repository_id=db_deployment.repository_id,
        provider=db_deployment.provider,
        external_id=db_deployment.external_id,
        environment=db_deployment.environment,
        sha=db_deployment.sha,
        status=DeploymentStatus(db_deployment.status),
        ref=db_deployment.ref,
        deployed_at=db_deployment.deployed_at,
        finished_at=db_deployment.finished_at,
        commits=tuple(commit_from_db(c) for c in db_deployment.commits),
        raw_data=db_deployment.raw_data or {},
    )


def incident_from_db(db_incident: "DBIncident") -> Incident:
    """Convert DB Incident to domain Incident."""
    # Note: DB Incident doesn't have deployment_id field (R1 links are in
    # incident_deployment_links table). R1 links will be loaded separately
    # via incident_deployment_links.
    return Incident(
        id=db_incident.id,
        repository_id=db_incident.repository_id,
        provider=db_incident.provider,
        external_id=db_incident.external_id,
        title=db_incident.title,
        state=IncidentState(db_incident.state),
        severity=(IncidentSeverity(db_incident.severity) if db_incident.severity else None),
        source=(
            IncidentSource(db_incident.source)
            if db_incident.source
            else IncidentSource.LABELED_ISSUE
        ),
        started_at=db_incident.started_at,
        resolved_at=db_incident.resolved_at,
        deployment_id=None,  # Not stored on DB Incident; loaded from links
        raw_data=db_incident.raw_data or {},
    )


def incident_deployment_link_from_db(db_link: "DBIncidentDeploymentLink") -> IncidentDeploymentLink:
    """Convert DB IncidentDeploymentLink to domain IncidentDeploymentLink."""
    return IncidentDeploymentLink(
        id=db_link.id,
        tenant_id=db_link.tenant_id,
        incident_id=db_link.incident_id,
        deployment_id=db_link.deployment_id,
        rule_id=LinkRule(db_link.rule_id),
        evidence=db_link.evidence or {},
        created_by=db_link.created_by,
        created_at=db_link.created_at,
    )

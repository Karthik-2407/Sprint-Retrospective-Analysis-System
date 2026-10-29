"""Core database models for DORA Platform.

All tables include tenant_id for multi-tenancy.
UUID primary keys used throughout.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Tenant(Base):
    """Tenant (organization/institution) — root of tenancy hierarchy."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    projects: Mapped[list["Project"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class Project(Base):
    """Project within a tenant (e.g., a course/cohort)."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)  # github | gitlab
    provider_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="projects")
    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    provider_connections: Mapped[list["ProviderConnection"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_projects_tenant_slug"),)


class Repository(Base):
    """Repository within a project."""

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="repositories")
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    commits: Mapped[list["Commit"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_id",
            name="uq_repositories_tenant_provider_external",
        ),
        Index("ix_repositories_project_provider", "project_id", "provider"),
        Index("ix_repositories_tenant_provider", "tenant_id", "provider"),
    )


class ProviderConnection(Base):
    """Authenticated provider connection (GitHub App installation, GitLab token)."""

    __tablename__ = "provider_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    # installation ID, project/group ID
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # GitHub App installation ID
    installation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    credentials_encrypted: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="provider_connections")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_id",
            name="uq_provider_connections_tenant_provider_external",
        ),
    )


class RawEvent(Base):
    """Append-only log of every webhook payload received. Never modified after insert."""

    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    # pull_request, deployment, etc.
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # X-GitHub-Delivery, X-Gitlab-Delivery
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of raw payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "delivery_id",
            name="uq_raw_events_tenant_provider_delivery",
        ),
        Index("ix_raw_events_tenant_received", "tenant_id", "received_at"),
    )


class QuarantinedEvent(Base):
    """Events that failed normalization. Never crash the worker."""

    __tablename__ = "quarantined_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_quarantined_events_tenant_received", "tenant_id", "received_at"),)


class PullRequest(Base):
    """Provider-neutral representation of PRs/MRs."""

    __tablename__ = "pull_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # PR/MR number
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)  # open, closed, merged
    # merge, squash, rebase
    merge_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    commits: Mapped[list["Commit"]] = relationship(
        secondary="pr_commits",
        back_populates="pull_requests",
        order_by="PRCommit.position",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_id",
            name="uq_pull_requests_tenant_provider_external",
        ),
        Index("ix_pull_requests_tenant_merged", "tenant_id", "merged_at"),
        Index("ix_pull_requests_repo_merged", "repository_id", "merged_at"),
    )


class Commit(Base):
    """Individual commits (shared across PRs and deployments)."""

    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_email: Mapped[str] = mapped_column(String(255), nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="commits")
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        secondary="pr_commits",
        back_populates="commits",
        order_by="PRCommit.position",
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        secondary="deployment_commits",
        back_populates="commits",
        order_by="DeploymentCommit.position",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "repository_id",
            "sha",
            name="uq_commits_tenant_repo_sha",
        ),
        Index("ix_commits_tenant_authored", "tenant_id", "authored_at"),
    )


class PRCommit(Base):
    """Join table: PR → commits (ordered by position in the PR)."""

    __tablename__ = "pr_commits"

    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_requests.id", ondelete="CASCADE"), primary_key=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Deployment(Base):
    """Provider-neutral representation of deployments."""

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # deployment ID
    # production, staging, etc.
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)  # deployed commit SHA
    # success, failed, cancelled, pending
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # branch/tag ref
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="deployments")
    commits: Mapped[list["Commit"]] = relationship(
        secondary="deployment_commits",
        back_populates="deployments",
        order_by="DeploymentCommit.position",
    )
    incident_links: Mapped[list["IncidentDeploymentLink"]] = relationship(
        back_populates="deployment", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_id",
            name="uq_deployments_tenant_provider_external",
        ),
        Index("ix_deployments_tenant_deployed", "tenant_id", "deployed_at"),
        Index("ix_deployments_repo_env_deployed", "repository_id", "environment", "deployed_at"),
        Index("ix_deployments_tenant_env_status", "tenant_id", "environment", "status"),
    )


class DeploymentCommit(Base):
    """Join table: deployment → commits (SHA range between consecutive successful deployments)."""

    __tablename__ = "deployment_commits"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), primary_key=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Incident(Base):
    """Provider-neutral representation of incidents."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab | manual
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # issue/incident number
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)  # open, closed, resolved
    # critical, high, medium, low
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # labeled_issue, native_incident, manual
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="incidents")
    deployment_links: Mapped[list["IncidentDeploymentLink"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_id",
            name="uq_incidents_tenant_provider_external",
        ),
        Index("ix_incidents_tenant_started", "tenant_id", "started_at"),
        Index("ix_incidents_repo_started", "repository_id", "started_at"),
        Index("ix_incidents_tenant_resolved", "tenant_id", "resolved_at"),
    )


class IncidentDeploymentLink(Base):
    """Explicit, auditable links between incidents and deployments. Strict linking only."""

    __tablename__ = "incident_deployment_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False)  # R1, R2, R3
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)  # system | manual
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="deployment_links")
    deployment: Mapped["Deployment"] = relationship(back_populates="incident_links")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "incident_id",
            "deployment_id",
            name="uq_incident_deployment_links_tenant_incident_deployment",
        ),
        Index("ix_incident_deployment_links_incident", "incident_id"),
        Index("ix_incident_deployment_links_deployment", "deployment_id"),
    )


class MetricSnapshot(Base):
    """Versioned, immutable metric computations. Never overwritten."""

    __tablename__ = "metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # tenant, project, repository
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # deployment_frequency, lead_time, etc.
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    # rolling_28d, rolling_90d, calendar_week, calendar_month
    window_type: Mapped[str] = mapped_column(String(20), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # e.g., "ADR-0003@2"
    definition_version: Mapped[str] = mapped_column(String(100), nullable=False)
    # ok, no_events, undetectable, insufficient_sample, partial_data
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # count, seconds, percentage
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, nullable=False
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope",
            "scope_id",
            "metric",
            "window_type",
            "window_start",
            "window_end",
            "definition_version",
            name="uq_metric_snapshots_unique",
        ),
        Index("ix_metric_snapshots_tenant_window", "tenant_id", "window_start", "window_end"),
        Index(
            "ix_metric_snapshots_tenant_metric_window",
            "tenant_id",
            "metric",
            "window_type",
            "window_start",
        ),
    )


class IngestionRun(Base):
    """Audit trail for backfill/reconcile jobs. Supports resumable backfill via cursor."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # github | gitlab
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)  # backfill, reconcile
    # running, completed, failed, partial
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    events_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="ingestion_runs")
    repository: Mapped["Repository"] = relationship(back_populates="ingestion_runs")

    # Constraints
    __table_args__ = (
        Index("ix_ingestion_runs_tenant_started", "tenant_id", "started_at"),
        Index("ix_ingestion_runs_project_provider_type", "project_id", "provider", "run_type"),
    )

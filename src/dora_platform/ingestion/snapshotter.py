"""Snapshotter — computes and persists metric snapshots.

Computes all metrics for a tenant/scope/window and upserts into
metric_snapshots with definition_version. Idempotent: same inputs
→ same snapshot (unique constraint prevents duplicates).
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    MetricSnapshot,
    Repository,
)
from dora_platform.db.models import (
    PullRequest as DBPullRequest,
)
from dora_platform.domain.models import (
    Deployment,
    Incident,
    IncidentDeploymentLink,
    PullRequest,
    Window,
    deployment_from_db,
    incident_deployment_link_from_db,
    incident_from_db,
    pull_request_from_db,
)
from dora_platform.linking.engine import LinkingEngine
from dora_platform.metrics import (
    compute_both_lead_times,
    compute_change_failure_rate,
    compute_deployment_frequency_with_days,
    compute_deployment_rework_rate,
    compute_failed_deployment_recovery_time,
)
from dora_platform.metrics.contract import MetricValue


class Snapshotter:
    """Computes and persists metric snapshots for a tenant."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        linking_engine: LinkingEngine | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.linking_engine = linking_engine or LinkingEngine(r3_enabled=False)

    async def _load_data(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        window: Window,
    ) -> dict[str, Any]:
        """Load all data needed for metric computation."""
        # Build base query for deployments with eager loading of commits
        dep_query = select(DBDeployment).options(
            selectinload(DBDeployment.commits)
        ).where(DBDeployment.tenant_id == self.tenant_id)
        if scope == "project" and scope_id:
            # Get repositories for this project
            repo_query = select(Repository.id).where(Repository.project_id == scope_id)
            repo_result = await self.session.execute(repo_query)
            repo_ids = [r[0] for r in repo_result.fetchall()]
            dep_query = dep_query.where(DBDeployment.repository_id.in_(repo_ids))
        elif scope == "repository" and scope_id:
            dep_query = dep_query.where(DBDeployment.repository_id == scope_id)

        dep_result = await self.session.execute(dep_query)
        db_deployments = list(dep_result.scalars().all())
        deployments = [deployment_from_db(d) for d in db_deployments]

        # Load PRs with eager loading of commits
        pr_query = select(DBPullRequest).options(
            selectinload(DBPullRequest.commits)
        ).where(DBPullRequest.tenant_id == self.tenant_id)
        if scope == "project" and scope_id:
            repo_query = select(Repository.id).where(Repository.project_id == scope_id)
            repo_result = await self.session.execute(repo_query)
            repo_ids = [r[0] for r in repo_result.fetchall()]
            pr_query = pr_query.where(DBPullRequest.repository_id.in_(repo_ids))
        elif scope == "repository" and scope_id:
            pr_query = pr_query.where(DBPullRequest.repository_id == scope_id)

        pr_result = await self.session.execute(pr_query)
        db_prs = list(pr_result.scalars().all())
        prs = [pull_request_from_db(p) for p in db_prs]

        # Load incidents
        inc_query = select(DBIncident).where(DBIncident.tenant_id == self.tenant_id)
        if scope == "project" and scope_id:
            repo_query = select(Repository.id).where(Repository.project_id == scope_id)
            repo_result = await self.session.execute(repo_query)
            repo_ids = [r[0] for r in repo_result.fetchall()]
            inc_query = inc_query.where(DBIncident.repository_id.in_(repo_ids))
        elif scope == "repository" and scope_id:
            inc_query = inc_query.where(DBIncident.repository_id == scope_id)

        inc_result = await self.session.execute(inc_query)
        db_incidents = list(inc_result.scalars().all())
        incidents = [incident_from_db(i) for i in db_incidents]

        # Load incident-deployment links
        link_query = select(DBIncidentDeploymentLink).where(
            DBIncidentDeploymentLink.tenant_id == self.tenant_id
        )
        link_result = await self.session.execute(link_query)
        db_incident_links = list(link_result.scalars().all())
        incident_links = [incident_deployment_link_from_db(link) for link in db_incident_links]

        return {
            "deployments": deployments,
            "prs": prs,
            "incidents": incidents,
            "incident_links": incident_links,
        }

    async def compute_snapshots(
        self,
        scope: str = "tenant",  # tenant, project, repository
        scope_id: uuid.UUID | None = None,
        window_types: list[str] | None = None,
    ) -> list[MetricSnapshot]:
        """Compute all metric snapshots for a scope and window types.

        Args:
            scope: "tenant", "project", or "repository"
            scope_id: UUID of project or repository (None for tenant scope)
            window_types: List of window types to compute
                (default: rolling_28d, rolling_90d, calendar_week, calendar_month)

        Returns:
            List of MetricSnapshot objects that were upserted
        """
        if window_types is None:
            window_types = ["rolling_28d", "rolling_90d", "calendar_week", "calendar_month"]

        now = datetime.now(tz=datetime.now().astimezone().tzinfo)
        windows = self._generate_windows(window_types, now)

        # Load all data once
        max_window = Window(
            window_types[0],
            datetime.min,
            datetime.max,
        )
        data = await self._load_data(scope, scope_id, max_window)
        deployments = data["deployments"]
        prs = data["prs"]
        incidents = data["incidents"]
        incident_links = data["incident_links"]

        snapshots = []

        for window in windows:
            # Compute all metrics for this window
            metric_values = await self._compute_all_metrics(
                deployments=deployments,
                prs=prs,
                incidents=incidents,
                incident_links=incident_links,
                window=window,
                now=now,
            )

            # Upsert each metric
            for metric_value in metric_values:
                snapshot = await self._upsert_snapshot(
                    scope=scope,
                    scope_id=scope_id,
                    metric_value=metric_value,
                    window=window,
                )
                snapshots.append(snapshot)

        await self.session.flush()
        return snapshots

    def _generate_windows(self, window_types: list[str], now: datetime) -> list[Window]:
        """Generate windows for the given types."""
        windows = []
        for wt in window_types:
            if wt == "rolling_28d":
                end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                start = end - timedelta(days=27)  # 28 days including today
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            elif wt == "rolling_90d":
                end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                start = end - timedelta(days=89)
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            elif wt == "calendar_week":
                # ISO week: Monday to Sunday
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                days_since_monday = start.weekday()
                start = start - timedelta(days=days_since_monday)
                end = start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
            elif wt == "calendar_month":
                # First to last day of current month
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if start.month == 12:
                    end = start.replace(
                        year=start.year + 1,
                        month=1,
                        day=1,
                        hour=23,
                        minute=59,
                        second=59,
                        microsecond=999999,
                    )
                else:
                    end = start.replace(
                        month=start.month + 1,
                        day=1,
                        hour=23,
                        minute=59,
                        second=59,
                        microsecond=999999,
                    )
            else:
                continue

            windows.append(Window(window_type=wt, start=start, end=end))

        return windows

    async def _compute_all_metrics(
        self,
        deployments: list[Deployment],
        prs: list[PullRequest],
        incidents: list[Incident],
        incident_links: list[IncidentDeploymentLink],
        window: Window,
        now: datetime,
    ) -> list[MetricValue]:
        """Compute all metric values for a window."""
        results: list[MetricValue] = []

        # Deployment frequency (with deploy days)
        freq_result: dict[str, MetricValue] = compute_deployment_frequency_with_days(
            deployments=deployments,
            window=window,
            now=now,
            source_configured=True,
            source_healthy=True,
        )
        results.extend(freq_result.values())

        # Lead times (both primary and secondary)
        lead_result: dict[str, MetricValue] = compute_both_lead_times(
            prs=prs,
            deployments=deployments,
            window=window,
            now=now,
            source_configured=True,
            source_healthy=True,
        )
        results.extend(lead_result.values())

        # Change failure rate
        cfr = compute_change_failure_rate(
            deployments=deployments,
            incidents=incidents,
            window=window,
            now=now,
            deployment_source_configured=True,
            deployment_source_healthy=True,
            incident_source_configured=True,
            incident_source_healthy=True,
            linking_engine=self.linking_engine,
        )
        results.append(cfr)

        # Failed deployment recovery time
        recovery = compute_failed_deployment_recovery_time(
            deployments=deployments,
            incidents=incidents,
            incident_links=incident_links,
            window=window,
            now=now,
            deployment_source_configured=True,
            deployment_source_healthy=True,
            incident_source_configured=True,
            incident_source_healthy=True,
            linking_engine=self.linking_engine,
        )
        results.append(recovery)

        # Deployment rework rate (PROPOSED)
        rework = compute_deployment_rework_rate(
            deployments=deployments,
            incident_links=incident_links,
            window=window,
            now=now,
            source_configured=True,
            source_healthy=True,
        )
        results.append(rework)

        return results

    async def _upsert_snapshot(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        metric_value: MetricValue,
        window: Window,
    ) -> MetricSnapshot:
        """Upsert a metric snapshot into the database."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        snapshot_data = {
            "tenant_id": self.tenant_id,
            "scope": scope,
            "scope_id": scope_id,
            "metric": metric_value.metric,
            "window_type": window.window_type,
            "window_start": window.start,
            "window_end": window.end,
            "definition_version": metric_value.definition_version,
            "status": metric_value.status.value,
            "value": metric_value.value,
            "unit": metric_value.unit,
            "n": metric_value.n,
            "evidence_ids": list(metric_value.evidence_ids),
            "extra_metadata": metric_value.extra or {},
        }

        stmt = (
            pg_insert(MetricSnapshot)
            .values(snapshot_data)
            .on_conflict_do_update(
                index_elements=[
                    "tenant_id",
                    "scope",
                    "scope_id",
                    "metric",
                    "window_type",
                    "window_start",
                    "window_end",
                    "definition_version",
                ],
                set_=snapshot_data,
            )
            .returning(MetricSnapshot)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()


async def recompute_all_snapshots(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    window_types: list[str] | None = None,
) -> list[MetricSnapshot]:
    """Convenience function to recompute all snapshots for a tenant."""
    snapshotter = Snapshotter(session, tenant_id)
    return await snapshotter.compute_snapshots(
        scope="tenant",
        scope_id=None,
        window_types=window_types,
    )

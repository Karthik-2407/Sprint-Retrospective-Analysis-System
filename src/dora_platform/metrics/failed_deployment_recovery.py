"""Failed deployment recovery time metric.

Per CLAUDE.md §3.1:
- Per failed deployment: service restored timestamp - failed deployment timestamp
- Using incident fields from the incident ADR
- Aggregate with median and p90
- No failed deployments in window → NO_EVENTS (never 0)
"""

import uuid
from datetime import datetime

import numpy as np

from dora_platform.domain.models import Deployment, Incident, IncidentDeploymentLink, Window
from dora_platform.linking.engine import LinkingEngine
from dora_platform.metrics.contract import MetricStatus, MetricValue

DEFINITION_VERSION = "ADR-0003@1"  # Incident/CFR definition version


def compute_failed_deployment_recovery_time(
    deployments: list[Deployment],
    incidents: list[Incident],
    incident_links: list[IncidentDeploymentLink] | None = None,
    window: Window | None = None,
    now: datetime | None = None,
    deployment_source_configured: bool = True,
    deployment_source_healthy: bool = True,
    incident_source_configured: bool = True,
    incident_source_healthy: bool = True,
    linking_engine: LinkingEngine | None = None,
) -> MetricValue:
    """Compute failed deployment recovery time (median and p90).

    Args:
        deployments: All deployments
        incidents: All incidents
        incident_links: Pre-computed incident-deployment links (optional)
        window: Time window (optional - if None, uses all failed deployments with links)
        now: Current time (injected)
        deployment_source_configured: Whether deployment source is configured
        deployment_source_healthy: Whether deployment source is healthy
        incident_source_configured: Whether incident source is configured
        incident_source_healthy: Whether incident source is healthy
        linking_engine: LinkingEngine instance (created with defaults if None)

    Returns:
        MetricValue with median and p90 recovery time in seconds
    """
    # Check deployment source
    if not deployment_source_configured:
        return MetricValue(
            metric="failed_deployment_recovery_time",
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start if window else datetime.min,
            window_end=window.end if window else datetime.max,
            definition_version=DEFINITION_VERSION,
            note="No deployment source configured",
        )

    if not deployment_source_healthy:
        return MetricValue(
            metric="failed_deployment_recovery_time",
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start if window else datetime.min,
            window_end=window.end if window else datetime.max,
            definition_version=DEFINITION_VERSION,
            note="Deployment source unhealthy",
        )

    # Check incident source
    if not incident_source_configured:
        return MetricValue(
            metric="failed_deployment_recovery_time",
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start if window else datetime.min,
            window_end=window.end if window else datetime.max,
            definition_version=DEFINITION_VERSION,
            note="No incident source configured",
        )

    if not incident_source_healthy:
        return MetricValue(
            metric="failed_deployment_recovery_time",
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start if window else datetime.min,
            window_end=window.end if window else datetime.max,
            definition_version=DEFINITION_VERSION,
            note="Incident source unhealthy",
        )

    # Filter to production deployments
    prod_deployments = [d for d in deployments if d.is_production]

    # If no pre-computed links, compute them
    if incident_links is None:
        if linking_engine is None:
            linking_engine = LinkingEngine(r3_enabled=False)

        # Filter incidents in window if provided
        if window:
            window_incidents = [
                inc
                for inc in incidents
                if inc.started_at is not None and window.start <= inc.started_at < window.end
            ]
        else:
            window_incidents = incidents

        incident_links = linking_engine.link_all(
            window_incidents,
            prod_deployments,
            uuid.UUID("00000000-0000-0000-0000-000000000000"),
        )

    # Get failed deployments
    failed_deployment_ids = set()
    for link in incident_links:
        failed_deployment_ids.add(link.deployment_id)

    # Find failed deployments with resolved incidents
    recovery_times = []
    evidence_ids = []

    for dep in prod_deployments:
        if dep.id not in failed_deployment_ids:
            continue

        if window and dep.deployed_at is not None:
            if not (window.start <= dep.deployed_at < window.end):
                continue

        # Get incidents linked to this deployment
        linked_incidents = [link for link in incident_links if link.deployment_id == dep.id]

        # Find the incident that represents the resolution
        # Use the earliest resolved incident linked to this deployment
        resolved_times = []
        for link in linked_incidents:
            incident = next((inc for inc in incidents if inc.id == link.incident_id), None)
            if incident and incident.is_resolved and incident.resolved_at is not None:
                if dep.finished_at is not None:
                    recovery_seconds = (incident.resolved_at - dep.finished_at).total_seconds()
                    if recovery_seconds >= 0:
                        resolved_times.append(recovery_seconds)

        if resolved_times:
            # Use the earliest resolution (first incident resolved)
            recovery_times.append(min(resolved_times))
            evidence_ids.append(str(dep.id))

    n = len(recovery_times)

    if n == 0:
        # Failed deployments exist but none have resolved incidents
        return MetricValue(
            metric="failed_deployment_recovery_time",
            value=None,
            unit="seconds",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start if window else datetime.min,
            window_end=window.end if window else datetime.max,
            definition_version=DEFINITION_VERSION,
            note="No failed deployments with resolved incidents in window",
            extra={
                "failed_deployments_count": len(failed_deployment_ids),
                "resolved_count": 0,
            },
        )

    # Compute statistics
    recovery_arr = np.array(recovery_times)
    median_rt = float(np.median(recovery_arr))
    p90_rt = float(np.percentile(recovery_arr, 90))

    return MetricValue(
        metric="failed_deployment_recovery_time",
        value=median_rt,
        unit="seconds",
        status=MetricStatus.OK,
        n=n,
        window_start=window.start if window else datetime.min,
        window_end=window.end if window else datetime.max,
        definition_version=DEFINITION_VERSION,
        evidence_ids=tuple(evidence_ids),
        extra={
            "p90": p90_rt,
            "failed_deployments_count": len(failed_deployment_ids),
            "resolved_count": n,
        },
    )

"""Deployment rework rate metric.

Per CLAUDE.md §3.2 (PROPOSED — needs ADR):
- Rework rate = unplanned deployments / total deployments
- Unplanned = a deployment made in response to a strictly linked production incident
- Distinct from CFR: CFR counts the *bad* deployment; rework rate counts the *fix* deployments
"""

from datetime import datetime

from dora_platform.domain.models import Deployment, IncidentDeploymentLink, Window
from dora_platform.metrics.contract import MetricStatus, MetricValue

DEFINITION_VERSION = "ADR-0004@1"  # Rework rate definition version (PROPOSED)


def compute_deployment_rework_rate(
    deployments: list[Deployment],
    incident_links: list[IncidentDeploymentLink],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> MetricValue:
    """Compute deployment rework rate.

    A rework deployment is a deployment that was triggered by a production incident.
    We identify these by checking if a deployment is marked as "unplanned" (not planned).
    The `is_planned` field should be provided in the deployment's raw_data.
    """
    if not source_configured:
        return MetricValue(
            metric="deployment_rework_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No deployment source configured",
        )

    if not source_healthy:
        return MetricValue(
            metric="deployment_rework_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="Deployment source unhealthy",
        )

    # Filter to production deployments in window
    prod_deployments = [
        d
        for d in deployments
        if d.is_production
        and d.deployed_at is not None
        and window.start <= d.deployed_at < window.end
    ]

    total_deployments = len(prod_deployments)

    if total_deployments == 0:
        return MetricValue(
            metric="deployment_rework_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No production deployments in window",
        )

    # Count unplanned deployments
    # A deployment is unplanned if is_planned is False in raw_data
    # Default to True (planned) if not specified
    unplanned_count = 0
    for dep in prod_deployments:
        is_planned = dep.raw_data.get("is_planned", True)
        if not is_planned:
            unplanned_count += 1

    rework_rate = (unplanned_count / total_deployments) * 100

    return MetricValue(
        metric="deployment_rework_rate",
        value=round(rework_rate, 2),
        unit="percentage",
        status=MetricStatus.OK,
        n=total_deployments,
        window_start=window.start,
        window_end=window.end,
        definition_version=DEFINITION_VERSION,
        note=None,
        extra={
            "unplanned_count": unplanned_count,
            "total_count": total_deployments,
        },
    )

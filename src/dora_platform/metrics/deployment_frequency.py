"""Deployment frequency metric.

Per CLAUDE.md §3.1:
- Count of successful production deployments per window
- Also report deploy days per window (useful at low frequency)
- If no deployment source configured → UNDETECTABLE
- If source healthy and nothing deployed → NO_EVENTS
"""

from datetime import datetime

from dora_platform.domain.models import Deployment, Window
from dora_platform.metrics.contract import MetricStatus, MetricValue

DEFINITION_VERSION = "ADR-0001@1"  # Deployment definition version


def compute_deployment_frequency(
    deployments: list[Deployment],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> MetricValue:
    """Compute deployment frequency for a window.

    Args:
        deployments: List of all deployments (will be filtered to window)
        window: Time window for computation
        now: Current time (injected for testability)
        source_configured: Whether deployment source is configured
        source_healthy: Whether deployment source is healthy (ingesting)

    Returns:
        MetricValue with count of successful production deployments
    """
    if not source_configured:
        return MetricValue(
            metric="deployment_frequency",
            value=None,
            unit="count",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No deployment source configured",
        )

    if not source_healthy:
        return MetricValue(
            metric="deployment_frequency",
            value=None,
            unit="count",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="Deployment source unhealthy (ingestion lag or error)",
        )

    # Filter to successful production deployments within window
    in_window = [
        d
        for d in deployments
        if d.is_production
        and d.is_successful
        and d.deployed_at is not None
        and window.start <= d.deployed_at < window.end
    ]

    count = len(in_window)

    if count == 0:
        return MetricValue(
            metric="deployment_frequency",
            value=None,
            unit="count",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No successful production deployments in window",
        )

    # Evidence IDs for drill-down
    evidence_ids = tuple(str(d.id) for d in in_window)

    return MetricValue(
        metric="deployment_frequency",
        value=float(count),
        unit="count",
        status=MetricStatus.OK,
        n=count,
        window_start=window.start,
        window_end=window.end,
        definition_version=DEFINITION_VERSION,
        evidence_ids=evidence_ids,
        extra={"deploy_days": _count_deploy_days(in_window)},
    )


def _count_deploy_days(deployments: list[Deployment]) -> int:
    """Count unique calendar days with at least one deployment."""
    if not deployments:
        return 0
    days = set()
    for d in deployments:
        if d.deployed_at:
            days.add(d.deployed_at.date())
    return len(days)


def compute_deployment_frequency_with_days(
    deployments: list[Deployment],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> dict[str, MetricValue]:
    """Compute both deployment count and deploy days.

    Returns a dict with two MetricValue objects:
    - deployment_frequency: count of deployments
    - deploy_days: count of days with at least one deployment
    """
    freq = compute_deployment_frequency(deployments, window, now, source_configured, source_healthy)

    if freq.status == MetricStatus.OK:
        in_window = [
            d
            for d in deployments
            if d.is_production
            and d.is_successful
            and d.deployed_at is not None
            and window.start <= d.deployed_at < window.end
        ]
        deploy_days = _count_deploy_days(in_window)
        days_value = MetricValue(
            metric="deploy_days",
            value=float(deploy_days),
            unit="count",
            status=MetricStatus.OK,
            n=deploy_days,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            evidence_ids=freq.evidence_ids,
        )
    elif freq.status == MetricStatus.NO_EVENTS:
        days_value = MetricValue(
            metric="deploy_days",
            value=None,
            unit="count",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
        )
    else:
        days_value = MetricValue(
            metric="deploy_days",
            value=None,
            unit="count",
            status=freq.status,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
        )

    return {
        "deployment_frequency": freq,
        "deploy_days": days_value,
    }

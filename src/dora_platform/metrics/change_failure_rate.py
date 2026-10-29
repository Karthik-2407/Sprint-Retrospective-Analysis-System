"""Change failure rate metric with strict linking.

Per CLAUDE.md §3.2:
- CFR = failed deployments / total production deployments
- A deployment is *failed* only if at least one incident is **explicitly linked**
- No time-window guessing, no "probably related", no counting unlinked incidents
- Incident source not configured/unhealthy → UNDETECTABLE
- Source healthy, deployments exist, zero linked incidents → genuine 0% with OK
- [PROPOSED] Wilson score interval next to the rate
"""

import uuid
from datetime import datetime

from dora_platform.domain.models import Deployment, Incident, Window
from dora_platform.linking.engine import LinkingEngine
from dora_platform.metrics.contract import MetricStatus, MetricValue
from dora_platform.stats.intervals import wilson_score_interval_percentage

DEFINITION_VERSION = "ADR-0003@1"  # Incident/CFR definition version


def compute_change_failure_rate(
    deployments: list[Deployment],
    incidents: list[Incident],
    window: Window,
    now: datetime | None = None,
    deployment_source_configured: bool = True,
    deployment_source_healthy: bool = True,
    incident_source_configured: bool = True,
    incident_source_healthy: bool = True,
    linking_engine: LinkingEngine | None = None,
) -> MetricValue:
    """Compute change failure rate with strict linking.

    Args:
        deployments: All deployments
        incidents: All incidents
        window: Time window
        now: Current time (injected)
        deployment_source_configured: Whether deployment source is configured
        deployment_source_healthy: Whether deployment source is healthy
        incident_source_configured: Whether incident source is configured
        incident_source_healthy: Whether incident source is healthy
        linking_engine: LinkingEngine instance (created with defaults if None)

    Returns:
        MetricValue with CFR percentage, Wilson interval, and counts
    """
    # Check deployment source
    if not deployment_source_configured:
        return MetricValue(
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No deployment source configured",
        )

    if not deployment_source_healthy:
        return MetricValue(
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="Deployment source unhealthy",
        )

    # Check incident source
    if not incident_source_configured:
        return MetricValue(
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No incident source configured",
        )

    if not incident_source_healthy:
        return MetricValue(
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="Incident source unhealthy",
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
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=DEFINITION_VERSION,
            note="No production deployments in window",
        )

    # Filter incidents in window (started within window)
    window_incidents = [
        inc
        for inc in incidents
        if inc.started_at is not None and window.start <= inc.started_at < window.end
    ]

    # Use linking engine to find incident-deployment links
    if linking_engine is None:
        linking_engine = LinkingEngine(r3_enabled=False)

    # Link all incidents to deployments
    incident_links = linking_engine.link_all(
        window_incidents,
        prod_deployments,
        uuid.UUID("00000000-0000-0000-0000-000000000000"),
    )

    # Get failed deployment IDs
    failed_deployment_ids = linking_engine.get_failed_deployments(prod_deployments, incident_links)
    failed_count = len(failed_deployment_ids)

    # Calculate CFR
    cfr = (failed_count / total_deployments) * 100

    # Wilson score interval
    wilson_ci = wilson_score_interval_percentage(failed_count, total_deployments)

    # Evidence IDs
    evidence_ids = tuple(str(d) for d in failed_deployment_ids)

    return MetricValue(
        metric="change_failure_rate",
        value=cfr,
        unit="percentage",
        status=MetricStatus.OK,
        n=total_deployments,
        window_start=window.start,
        window_end=window.end,
        definition_version=DEFINITION_VERSION,
        evidence_ids=evidence_ids,
        extra={
            "failed_count": failed_count,
            "total_count": total_deployments,
            "wilson_ci_lower": wilson_ci.lower,
            "wilson_ci_upper": wilson_ci.upper,
            "wilson_confidence": wilson_ci.confidence_level,
            "linked_incidents_count": len(incident_links),
            "incidents_in_window": len(window_incidents),
        },
    )

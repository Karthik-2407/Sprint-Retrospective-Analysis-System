"""Strict incident-to-deployment linking rules (R1, R2, R3).

Per CLAUDE.md §3.2: A deployment is *failed* only if at least one incident
is **explicitly linked** to it under the rules. No time-window guessing,
no "probably related", no counting unlinked incidents.

Rules:
- R1: Incident has explicit `deployment_id` field pointing to a deployment
- R2: Incident references deployment SHA in body/comments (regex match)
- R3: Incident opened within configurable window after failed deployment (opt-in)
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from dora_platform.domain.models import (
    Deployment,
    Incident,
    IncidentDeploymentLink,
    LinkRule,
)

# R2: Pattern to match deployment SHAs in incident body/comments
# Matches 7-40 character hex strings that look like git SHAs
SHA_PATTERN = re.compile(r"\b([0-9a-f]{7,40})\b", re.IGNORECASE)

# R2: Also match explicit "deployment SHA" or "deploy SHA" references
DEPLOYMENT_SHA_PATTERN = re.compile(
    r"(?:deployment|deploy)\s+(?:sha|id|commit)\s*[:\-]?\s*([0-9a-f]{7,40})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LinkEvidence:
    """Evidence for a link match."""

    rule: LinkRule
    matched_field: str  # e.g., "deployment_id", "body", "comment"
    matched_value: str  # what was matched
    pattern: str | None = None  # regex pattern used (for R2)
    deployment_sha: str | None = None  # the SHA that matched (for R2)
    time_delta_seconds: float | None = None  # for R3


def rule_r1_explicit(
    incident: Incident,
    deployments: list[Deployment],
) -> list[LinkEvidence]:
    """R1: Incident has explicit deployment_id field.

    This is the strongest link — the incident directly references a deployment.
    """
    evidence = []
    if incident.deployment_id is not None:
        # Find the deployment
        for dep in deployments:
            if dep.id == incident.deployment_id:
                evidence.append(
                    LinkEvidence(
                        rule=LinkRule.R1_EXPLICIT,
                        matched_field="deployment_id",
                        matched_value=str(incident.deployment_id),
                        deployment_sha=dep.sha,
                    )
                )
                break
    return evidence


def rule_r2_sha_reference(
    incident: Incident,
    deployments: list[Deployment],
) -> list[LinkEvidence]:
    """R2: Incident references deployment SHA in body/comments.

    Searches incident body and comments for deployment SHAs that match
    a failed or successful production deployment.
    """
    evidence = []

    # Build a map of SHA -> deployment for quick lookup
    # Only consider production deployments for linking
    prod_deployments = [d for d in deployments if d.is_production]
    sha_to_deployment = {d.sha.lower(): d for d in prod_deployments}

    # Search fields for SHA references
    search_fields = {
        "body": incident.raw_data.get("body", "") or "",
    }

    # Add comments if present
    comments = incident.raw_data.get("comments", [])
    if isinstance(comments, list):
        for i, comment in enumerate(comments):
            if isinstance(comment, dict):
                search_fields[f"comment_{i}"] = comment.get("body", "") or ""
            elif isinstance(comment, str):
                search_fields[f"comment_{i}"] = comment

    for field_name, field_value in search_fields.items():
        if not field_value:
            continue

        # Try explicit deployment SHA pattern first
        for match in DEPLOYMENT_SHA_PATTERN.finditer(field_value):
            sha = match.group(1).lower()
            if sha in sha_to_deployment:
                dep = sha_to_deployment[sha]
                evidence.append(
                    LinkEvidence(
                        rule=LinkRule.R2_SHA_REF,
                        matched_field=field_name,
                        matched_value=match.group(0),
                        pattern="deployment_sha_pattern",
                        deployment_sha=dep.sha,
                    )
                )

        # Try generic SHA pattern (more permissive)
        for match in SHA_PATTERN.finditer(field_value):
            sha = match.group(1).lower()
            if sha in sha_to_deployment:
                dep = sha_to_deployment[sha]
                evidence.append(
                    LinkEvidence(
                        rule=LinkRule.R2_SHA_REF,
                        matched_field=field_name,
                        matched_value=match.group(0),
                        pattern="generic_sha_pattern",
                        deployment_sha=dep.sha,
                    )
                )

    return evidence


def rule_r3_time_window(
    incident: Incident,
    deployments: list[Deployment],
    window_hours: int = 24,
) -> list[LinkEvidence]:
    """R3: Incident opened within window after a failed deployment.

    This is an opt-in rule (configurable window) that links incidents
    to the most recent failed production deployment before the incident.

    Only applies if R1 and R2 found no links.
    """
    evidence: list[LinkEvidence] = []

    if incident.started_at is None:
        return evidence

    # Only consider failed production deployments
    failed_prod = [
        d for d in deployments if d.is_production and d.is_failed and d.finished_at is not None
    ]

    if not failed_prod:
        return evidence

    # Sort by finished_at descending (most recent first)
    # All items have finished_at is not None due to filter above
    from datetime import datetime as dt_datetime

    failed_prod.sort(key=lambda d: d.finished_at or dt_datetime.min, reverse=True)

    window = timedelta(hours=window_hours)

    for dep in failed_prod:
        if dep.finished_at is None:
            continue

        delta = incident.started_at - dep.finished_at
        if timedelta(0) <= delta <= window:
            evidence.append(
                LinkEvidence(
                    rule=LinkRule.R3_WINDOW,
                    matched_field="started_at",
                    matched_value=incident.started_at.isoformat(),
                    deployment_sha=dep.sha,
                    time_delta_seconds=delta.total_seconds(),
                )
            )
            break  # Only link to the most recent failed deployment

    return evidence


def compute_links(
    incident: Incident,
    deployments: list[Deployment],
    r3_window_hours: int = 24,
) -> list[IncidentDeploymentLink]:
    """Compute all incident-deployment links using R1, R2, R3 in order.

    Rules are applied in priority order:
    1. R1 (explicit) — strongest, always wins if present
    2. R2 (SHA reference) — strong, requires SHA match in incident text
    3. R3 (time window) — opt-in, only if R1 and R2 found nothing

    Returns a list of IncidentDeploymentLink objects with evidence.
    """
    links = []

    # R1: Explicit deployment_id
    r1_evidence = rule_r1_explicit(incident, deployments)
    for ev in r1_evidence:
        links.append(
            IncidentDeploymentLink(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(
                    "00000000-0000-0000-0000-000000000000"
                ),  # placeholder, set by caller
                incident_id=incident.id,
                deployment_id=uuid.UUID(ev.matched_value),
                rule_id=LinkRule.R1_EXPLICIT,
                evidence={
                    "rule": ev.rule.value,
                    "matched_field": ev.matched_field,
                    "matched_value": ev.matched_value,
                    "deployment_sha": ev.deployment_sha,
                },
                created_by="system",
                created_at=datetime.now(tz=datetime.now().astimezone().tzinfo),
            )
        )

    # If R1 found links, stop here (R1 is authoritative)
    if links:
        return links

    # R2: SHA reference in body/comments
    r2_evidence = rule_r2_sha_reference(incident, deployments)
    for ev in r2_evidence:
        # Find the deployment ID for this SHA
        dep_id = None
        if ev.deployment_sha is not None:
            for d in deployments:
                if d.sha.lower() == ev.deployment_sha.lower():
                    dep_id = d.id
                    break
        if dep_id is None:
            continue

        links.append(
            IncidentDeploymentLink(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                incident_id=incident.id,
                deployment_id=dep_id,
                rule_id=LinkRule.R2_SHA_REF,
                evidence={
                    "rule": ev.rule.value,
                    "matched_field": ev.matched_field,
                    "matched_value": ev.matched_value,
                    "pattern": ev.pattern,
                    "deployment_sha": ev.deployment_sha,
                },
                created_by="system",
                created_at=datetime.now(tz=datetime.now().astimezone().tzinfo),
            )
        )

    # If R2 found links, stop here
    if links:
        return links

    # R3: Time window after failed deployment (opt-in)
    r3_evidence = rule_r3_time_window(incident, deployments, r3_window_hours)
    for ev in r3_evidence:
        dep_id = None
        if ev.deployment_sha is not None:
            for d in deployments:
                if d.sha.lower() == ev.deployment_sha.lower():
                    dep_id = d.id
                    break
        if dep_id is None:
            continue

        links.append(
            IncidentDeploymentLink(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                incident_id=incident.id,
                deployment_id=dep_id,
                rule_id=LinkRule.R3_WINDOW,
                evidence={
                    "rule": ev.rule.value,
                    "matched_field": ev.matched_field,
                    "matched_value": ev.matched_value,
                    "deployment_sha": ev.deployment_sha,
                    "time_delta_seconds": ev.time_delta_seconds,
                    "window_hours": r3_window_hours,
                },
                created_by="system",
                created_at=datetime.now(tz=datetime.now().astimezone().tzinfo),
            )
        )

    return links

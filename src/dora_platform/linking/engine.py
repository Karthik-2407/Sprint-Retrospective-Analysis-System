"""Linking engine — orchestrates incident-to-deployment linking.

This is the main entry point for computing incident-deployment links.
It applies rules in priority order (R1 > R2 > R3) and returns auditable links.
"""

import uuid
from typing import Any

from dora_platform.domain.models import (
    Deployment,
    Incident,
    IncidentDeploymentLink,
)
from dora_platform.linking.rules import compute_links


class LinkingEngine:
    """Engine for computing incident-deployment links.

    Configuration:
    - r3_enabled: Whether to apply R3 (time-window) rule
    - r3_window_hours: Time window for R3 rule (default 24 hours)
    """

    def __init__(
        self,
        r3_enabled: bool = False,
        r3_window_hours: int = 24,
    ) -> None:
        self.r3_enabled = r3_enabled
        self.r3_window_hours = r3_window_hours

    def link_incident(
        self,
        incident: Incident,
        deployments: list[Deployment],
        tenant_id: uuid.UUID,
    ) -> list[IncidentDeploymentLink]:
        """Compute links for a single incident against a list of deployments.

        Returns a list of IncidentDeploymentLink objects with evidence.
        The tenant_id is attached to each link.
        """
        # Filter to production deployments only for linking
        prod_deployments = [d for d in deployments if d.is_production]

        # Use the rules module to compute raw links
        raw_links = compute_links(
            incident=incident,
            deployments=prod_deployments,
            r3_window_hours=self.r3_window_hours if self.r3_enabled else 0,
        )

        # Attach tenant_id to each link
        linked = []
        for link in raw_links:
            linked.append(
                IncidentDeploymentLink(
                    id=link.id,
                    tenant_id=tenant_id,
                    incident_id=link.incident_id,
                    deployment_id=link.deployment_id,
                    rule_id=link.rule_id,
                    evidence=link.evidence,
                    created_by=link.created_by,
                    created_at=link.created_at,
                )
            )

        return linked

    def link_all(
        self,
        incidents: list[Incident],
        deployments: list[Deployment],
        tenant_id: uuid.UUID,
    ) -> list[IncidentDeploymentLink]:
        """Compute links for all incidents.

        Returns a flat list of all IncidentDeploymentLink objects.
        """
        all_links = []
        for incident in incidents:
            links = self.link_incident(incident, deployments, tenant_id)
            all_links.extend(links)
        return all_links

    def get_failed_deployments(
        self,
        deployments: list[Deployment],
        incident_links: list[IncidentDeploymentLink],
    ) -> set[uuid.UUID]:
        """Get the set of deployment IDs that have at least one linked incident.

        These are the "failed" deployments per strict linking definition.
        """
        failed = set()
        for link in incident_links:
            failed.add(link.deployment_id)
        return failed

    def get_incidents_for_deployment(
        self,
        deployment_id: uuid.UUID,
        incident_links: list[IncidentDeploymentLink],
    ) -> list[IncidentDeploymentLink]:
        """Get all links for a specific deployment."""
        return [link for link in incident_links if link.deployment_id == deployment_id]


def create_linking_engine_from_config(config: dict[str, Any]) -> LinkingEngine:
    """Factory function to create LinkingEngine from configuration dict.

    Expected config keys:
    - r3_enabled: bool (default False)
    - r3_window_hours: int (default 24)
    """
    return LinkingEngine(
        r3_enabled=config.get("r3_enabled", False),
        r3_window_hours=config.get("r3_window_hours", 24),
    )

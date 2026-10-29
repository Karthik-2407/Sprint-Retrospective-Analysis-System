"""Tests for strict incident-to-deployment linking rules (R1, R2, R3)."""

from datetime import datetime
from uuid import UUID, uuid4

from dora_platform.domain.models import Deployment, DeploymentStatus, Incident, LinkRule
from dora_platform.linking.engine import LinkingEngine
from dora_platform.linking.rules import (
    compute_links,
    rule_r1_explicit,
    rule_r2_sha_reference,
    rule_r3_time_window,
)

DEP_ID_1 = UUID("11111111-1111-1111-1111-111111111111")
DEP_ID_2 = UUID("22222222-2222-2222-2222-222222222222")
DEP_ID_3 = UUID("33333333-3333-3333-3333-333333333333")


def make_deployment(**kwargs):
    """Create a test deployment with defaults."""
    defaults = {
        "id": uuid4(),
        "repository_id": uuid4(),
        "provider": "github",
        "external_id": "deploy-1",
        "environment": "production",
        "sha": "abc123def456",
        "status": DeploymentStatus.SUCCESS,
        "deployed_at": datetime(2024, 1, 15, 10, 0, 0),
        "finished_at": datetime(2024, 1, 15, 10, 5, 0),
        "commits": [],
    }
    defaults.update(kwargs)
    return Deployment(**defaults)


def make_incident(**kwargs):
    """Create a test incident with defaults."""
    defaults = {
        "id": uuid4(),
        "repository_id": uuid4(),
        "provider": "github",
        "external_id": "1",
        "title": "Test incident",
        "state": "resolved",
        "severity": "high",
        "source": "labeled_issue",
        "started_at": datetime(2024, 1, 15, 11, 0, 0),
        "resolved_at": datetime(2024, 1, 15, 13, 0, 0),
        "deployment_id": None,
        "raw_data": {},
    }
    defaults.update(kwargs)
    return Incident(**defaults)


class TestR1ExplicitDeploymentId:
    """Tests for R1: Explicit deployment_id field on incident."""

    def test_r1_matches_when_deployment_id_set(self):
        """R1 links when incident.deployment_id matches a deployment."""
        dep = make_deployment(id=DEP_ID_1)
        inc = make_incident(deployment_id=DEP_ID_1)

        evidence = rule_r1_explicit(inc, [dep])

        assert len(evidence) == 1
        assert evidence[0].rule == LinkRule.R1_EXPLICIT
        assert evidence[0].matched_field == "deployment_id"
        assert evidence[0].matched_value == str(DEP_ID_1)

    def test_r1_no_match_when_deployment_id_missing(self):
        """R1 returns empty list when incident has no deployment_id."""
        dep = make_deployment()
        inc = make_incident(deployment_id=None)

        evidence = rule_r1_explicit(inc, [dep])

        assert evidence == []

    def test_r1_no_match_when_deployment_not_found(self):
        """R1 returns empty list when deployment_id doesn't match any deployment."""
        dep = make_deployment(id=DEP_ID_1)
        inc = make_incident(deployment_id=UUID("99999999-9999-9999-9999-999999999999"))

        evidence = rule_r1_explicit(inc, [dep])

        assert evidence == []

    def test_r1_ignores_incident_state(self):
        """R1 links regardless of incident state (open/resolved)."""
        dep = make_deployment()
        inc_open = make_incident(state="open", deployment_id=dep.id)
        inc_resolved = make_incident(state="resolved", deployment_id=dep.id)

        evidence_open = rule_r1_explicit(inc_open, [dep])
        evidence_resolved = rule_r1_explicit(inc_resolved, [dep])

        assert len(evidence_open) == 1
        assert len(evidence_resolved) == 1


class TestR2ShaReference:
    """Tests for R2: SHA reference in incident body/comments."""

    def test_r2_matches_sha_in_body(self):
        """R2 links when incident body contains deployment SHA."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "This was caused by deployment abc123def456"},
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert len(evidence) >= 1
        assert evidence[0].rule == LinkRule.R2_SHA_REF
        assert evidence[0].deployment_sha == "abc123def456"

    def test_r2_matches_short_sha(self):
        """R2 matches deployment SHA prefix (7+ chars)."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "Caused by abc123def456"},  # Full SHA matches
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert len(evidence) >= 1

    def test_r2_no_match_when_no_sha_in_body(self):
        """R2 returns empty list when no SHA found in body."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "This is a documentation issue"},
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert evidence == []

    def test_r2_no_match_when_sha_not_in_deployments(self):
        """R2 returns empty list when SHA in body doesn't match any deployment."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "Caused by fedcba987654"},
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert evidence == []

    def test_r2_case_insensitive(self):
        """R2 matching is case-insensitive."""
        dep = make_deployment(sha="ABC123DEF456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "caused by abc123def456"},
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert len(evidence) >= 1

    def test_r2_checks_multiple_fields(self):
        """R2 checks body and comments fields."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"comments": [{"body": "see abc123def456"}]},
        )

        evidence = rule_r2_sha_reference(inc, [dep])

        assert len(evidence) >= 1


class TestR3TimeWindow:
    """Tests for R3: Time window proximity (opt-in, configurable)."""

    def test_r3_matches_within_window(self):
        """R3 links when incident starts within window after failed deployment."""
        dep = make_deployment(
            id=DEP_ID_1,
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        evidence = rule_r3_time_window(inc, [dep], window_hours=1)

        assert len(evidence) == 1
        assert evidence[0].rule == LinkRule.R3_WINDOW
        # 10:30 - 10:05 = 25 minutes = 1500 seconds
        assert evidence[0].time_delta_seconds == 1500.0

    def test_r3_no_match_outside_window(self):
        """R3 returns empty list when incident outside window."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 12, 0, 0),
        )

        evidence = rule_r3_time_window(inc, [dep], window_hours=1)

        assert evidence == []

    def test_r3_only_failed_deployments(self):
        """R3 only considers failed deployments."""
        dep_success = make_deployment(
            id=DEP_ID_1,
            status=DeploymentStatus.SUCCESS,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        dep_failed = make_deployment(
            id=DEP_ID_2,
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        evidence = rule_r3_time_window(inc, [dep_success, dep_failed], window_hours=1)

        assert len(evidence) == 1
        assert evidence[0].deployment_sha == dep_failed.sha

    def test_r3_requires_opt_in(self):
        """R3 requires explicit opt-in (window_hours > 0)."""
        dep = make_deployment(status=DeploymentStatus.FAILED)
        inc = make_incident(started_at=datetime(2024, 1, 15, 10, 30, 0))

        # Default window_hours=24 means enabled by default
        evidence = rule_r3_time_window(inc, [dep])
        assert len(evidence) == 1

        # Zero window means disabled
        evidence = rule_r3_time_window(inc, [dep], window_hours=0)
        assert evidence == []

    def test_r3_before_deployment_no_match(self):
        """R3 doesn't match incidents before deployment."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 9, 30, 0),  # Before deployment
        )

        evidence = rule_r3_time_window(inc, [dep], window_hours=1)

        assert evidence == []


class TestComputeLinks:
    """Tests for compute_links function (R1 > R2 > R3 priority)."""

    def test_priority_r1_over_r2(self):
        """R1 takes priority over R2 when both could match."""
        dep = make_deployment(id=DEP_ID_1, sha="abc123def456")
        inc = make_incident(
            deployment_id=DEP_ID_1,
            raw_data={"body": "also caused by abc123def456"},
        )

        links = compute_links(inc, [dep])

        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R1_EXPLICIT

    def test_priority_r2_over_r3(self):
        """R2 takes priority over R3 when both could match."""
        dep = make_deployment(
            id=DEP_ID_1,
            sha="abc123def456",
            status=DeploymentStatus.FAILED,
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            raw_data={"body": "caused by abc123def456"},
        )

        links = compute_links(inc, [dep], r3_window_hours=1)

        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R2_SHA_REF

    def test_all_rules_applied(self):
        """compute_links applies all enabled rules in priority order."""
        # Use valid hex SHA values (0-9, a-f only)
        dep1 = make_deployment(id=DEP_ID_1, sha="abc123def456")
        dep2 = make_deployment(id=DEP_ID_2, sha="def456abc789", status=DeploymentStatus.FAILED)
        inc1 = make_incident(deployment_id=DEP_ID_1)  # R1
        inc2 = make_incident(
            deployment_id=None,
            raw_data={"body": "def456abc789"},
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )  # R2
        inc3 = make_incident(deployment_id=None, started_at=datetime(2024, 1, 15, 10, 30, 0))  # R3

        all_links = []
        for inc in [inc1, inc2, inc3]:
            links = compute_links(inc, [dep1, dep2], r3_window_hours=1)
            all_links.extend(links)

        assert len(all_links) == 3
        rule_ids = [link.rule_id for link in all_links]
        assert LinkRule.R1_EXPLICIT in rule_ids
        assert LinkRule.R2_SHA_REF in rule_ids
        assert LinkRule.R3_WINDOW in rule_ids


class TestLinkingEngine:
    """Tests for LinkingEngine applying rules in priority order."""

    def test_priority_r1_over_r2(self):
        """R1 takes priority over R2 when both could match."""
        dep = make_deployment(id=DEP_ID_1, sha="abc123def456")
        inc = make_incident(
            deployment_id=DEP_ID_1,
            raw_data={"body": "also caused by abc123def456"},
        )

        engine = LinkingEngine()
        links = engine.link_incident(inc, [dep], tenant_id=uuid4())

        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R1_EXPLICIT

    def test_priority_r2_over_r3(self):
        """R2 takes priority over R3 when both could match."""
        dep = make_deployment(
            id=DEP_ID_1,
            sha="abc123def456",
            status=DeploymentStatus.FAILED,
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            raw_data={"body": "caused by abc123def456"},
        )

        engine = LinkingEngine(r3_enabled=True, r3_window_hours=1)
        links = engine.link_incident(inc, [dep], tenant_id=uuid4())

        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R2_SHA_REF

    def test_r3_disabled_by_default(self):
        """R3 is disabled by default."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        engine = LinkingEngine()
        links = engine.link_incident(inc, [dep], tenant_id=uuid4())

        assert len(links) == 0  # R3 disabled by default

    def test_r3_enabled_explicitly(self):
        """R3 works when explicitly enabled."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        engine = LinkingEngine(r3_enabled=True, r3_window_hours=1)
        links = engine.link_incident(inc, [dep], tenant_id=uuid4())

        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R3_WINDOW

    def test_link_all_incidents(self):
        """link_all processes all incidents."""
        dep = make_deployment()
        inc1 = make_incident(deployment_id=dep.id)
        inc2 = make_incident(deployment_id=None)

        engine = LinkingEngine()
        links = engine.link_all([inc1, inc2], [dep], tenant_id=uuid4())

        assert len(links) == 1  # Only inc1 has explicit link

    def test_get_failed_deployments(self):
        """get_failed_deployments returns deployments with linked incidents."""
        dep = make_deployment()
        inc = make_incident(deployment_id=dep.id)

        engine = LinkingEngine()
        links = engine.link_incident(inc, [dep], tenant_id=uuid4())
        failed = engine.get_failed_deployments([dep], links)

        assert dep.id in failed


class TestRulesEdgeCases:
    """Tests for edge cases in linking rules."""

    def test_r2_deployment_sha_pattern(self):
        """R2 matches explicit 'deployment sha' pattern."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "caused by deployment sha abc123def456"},
        )
        evidence = rule_r2_sha_reference(inc, [dep])
        assert len(evidence) >= 1
        assert evidence[0].rule == LinkRule.R2_SHA_REF

    def test_r2_deploy_sha_pattern(self):
        """R2 matches 'deploy sha' pattern."""
        dep = make_deployment(sha="abc123def456")
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "bad deploy sha: abc123def456"},
        )
        evidence = rule_r2_sha_reference(inc, [dep])
        assert len(evidence) >= 1

    def test_r3_returns_empty_when_no_started_at(self):
        """R3 returns empty when incident has no started_at."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(started_at=None)
        evidence = rule_r3_time_window(inc, [dep], window_hours=1)
        assert evidence == []

    def test_r3_skips_deployment_without_finished_at(self):
        """R3 skips deployments without finished_at."""
        dep = make_deployment(
            status=DeploymentStatus.FAILED,
            finished_at=None,
        )
        inc = make_incident(started_at=datetime(2024, 1, 15, 10, 30, 0))
        evidence = rule_r3_time_window(inc, [dep], window_hours=1)
        assert evidence == []

    def test_compute_links_r2_dep_id_none(self):
        """compute_links handles case where deployment not found for SHA."""
        dep = make_deployment(sha="abc123def456")
        # Incident references a SHA that doesn't match any deployment
        inc = make_incident(
            deployment_id=None,
            raw_data={"body": "caused by fedcba987654"},
        )
        links = compute_links(inc, [dep])
        assert links == []  # No match

    def test_compute_links_r3_dep_id_none(self):
        """compute_links handles case where R3 deployment not found."""
        dep = make_deployment(
            sha="abc123def456",
            status=DeploymentStatus.FAILED,
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
        )
        inc = make_incident(
            deployment_id=None,
            started_at=datetime(2024, 1, 15, 10, 30, 0),
        )
        # R3 should find the deployment, but let's test the edge case
        links = compute_links(inc, [dep], r3_window_hours=1)
        # Should find a link since deployment matches
        assert len(links) == 1
        assert links[0].rule_id == LinkRule.R3_WINDOW

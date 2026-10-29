"""Tests for failed deployment recovery time metric using golden dataset."""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dora_platform.domain.models import (
    Deployment,
    DeploymentStatus,
    Incident,
    IncidentDeploymentLink,
    Window,
)
from dora_platform.metrics.contract import MetricStatus
from dora_platform.metrics.failed_deployment_recovery import compute_failed_deployment_recovery_time

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden" / "recovery_time_golden.json"


def load_golden():
    """Load golden dataset."""
    with FIXTURE_PATH.open() as f:
        return json.load(f)


def parse_deployment(data: dict) -> Deployment:
    """Parse deployment from golden fixture format."""
    return Deployment(
        id=data["id"],
        repository_id=data["repository_id"],
        provider=data["provider"],
        external_id=data["external_id"],
        environment=data["environment"],
        sha=data["sha"],
        status=data["status"],
        deployed_at=datetime.fromisoformat(data["deployed_at"]).replace(tzinfo=None),
        finished_at=(
            datetime.fromisoformat(data["finished_at"]).replace(tzinfo=None)
            if data.get("finished_at")
            else None
        ),
        commits=[],
    )


def parse_incident(data: dict) -> Incident:
    """Parse incident from golden fixture format."""
    return Incident(
        id=data["id"],
        repository_id=data["repository_id"],
        provider=data["provider"],
        external_id=data["external_id"],
        title=data["title"],
        state=data["state"],
        severity=data.get("severity"),
        source=data.get("source"),
        started_at=datetime.fromisoformat(data["started_at"]).replace(tzinfo=None),
        resolved_at=(
            datetime.fromisoformat(data["resolved_at"]).replace(tzinfo=None)
            if data.get("resolved_at")
            else None
        ),
        deployment_id=data.get("deployment_id"),
        raw_data=data.get("raw_data", {}),
    )


def parse_incident_link(data: dict) -> IncidentDeploymentLink:
    """Parse incident link from golden fixture format."""
    return IncidentDeploymentLink(
        id=data["id"],
        tenant_id=data["tenant_id"],
        incident_id=data["incident_id"],
        deployment_id=data["deployment_id"],
        rule_id=data["rule_id"],
        evidence=data.get("evidence", {}),
        created_by=data.get("created_by", "system"),
        created_at=(
            datetime.fromisoformat(data["created_at"]).replace(tzinfo=None)
            if data.get("created_at")
            else None
        ),
    )


def parse_window(data: dict) -> Window:
    """Parse window from golden fixture format."""
    return Window(
        window_type=data.get("window_type", "rolling_28d"),
        start=datetime.fromisoformat(data["start"]).replace(tzinfo=None),
        end=datetime.fromisoformat(data["end"]).replace(tzinfo=None),
    )


class TestRecoveryTimeGolden:
    """Test failed deployment recovery time against golden dataset."""

    @pytest.fixture
    def golden(self):
        return load_golden()

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "single_recovery"},
            {"name": "multiple_recoveries"},
            {"name": "unresolved_incident"},
            {"name": "no_incidents"},
        ],
    )
    def test_golden_cases(self, golden, test_case):
        """Run each golden test case."""
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        deployments = [parse_deployment(d) for d in tc.get("deployments", [])]
        incidents = [parse_incident(i) for i in tc.get("incidents", [])]
        incident_links = [parse_incident_link(link) for link in tc.get("incident_links", [])]
        window = parse_window(tc["window"])
        expected = tc["expected"]

        result = compute_failed_deployment_recovery_time(
            deployments=deployments,
            incidents=incidents,
            incident_links=incident_links,
            window=window,
        )

        assert result.metric == expected["metric"]
        assert result.status == MetricStatus(expected["status"])
        assert result.n == expected["n"]
        assert result.unit == expected["unit"]
        assert result.window_start == window.start
        assert result.window_end == window.end

        if expected["value"] is None:
            assert result.value is None
        else:
            assert abs(result.value - expected["value"]) < 0.01, (
                f"Expected {expected['value']}, got {result.value}"
            )

        if expected["note"]:
            assert expected["note"] in (result.note or "")

        # Check p90 if present
        if "p90" in expected and expected["p90"] is not None:
            assert result.extra is not None
            assert "p90" in result.extra
            assert abs(result.extra["p90"] - expected["p90"]) < 0.01


class TestRecoveryTimeSource:
    """Test source configuration handling."""

    def test_undetectable_when_deployment_source_not_configured(self):
        """Returns UNDETECTABLE when deployment_source_configured=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_failed_deployment_recovery_time(
            deployments=[],
            incidents=[],
            window=window,
            deployment_source_configured=False,
        )
        assert result.status == MetricStatus.UNDETECTABLE
        assert "No deployment source configured" in (result.note or "")

    def test_undetectable_when_deployment_source_unhealthy(self):
        """Returns UNDETECTABLE when deployment_source_healthy=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_failed_deployment_recovery_time(
            deployments=[],
            incidents=[],
            window=window,
            deployment_source_healthy=False,
        )
        assert result.status == MetricStatus.UNDETECTABLE
        assert "Deployment source unhealthy" in (result.note or "")

    def test_undetectable_when_incident_source_not_configured(self):
        """Returns UNDETECTABLE when incident_source_configured=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_failed_deployment_recovery_time(
            deployments=[],
            incidents=[],
            window=window,
            incident_source_configured=False,
        )
        assert result.status == MetricStatus.UNDETECTABLE
        assert "No incident source configured" in (result.note or "")

    def test_undetectable_when_incident_source_unhealthy(self):
        """Returns UNDETECTABLE when incident_source_healthy=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_failed_deployment_recovery_time(
            deployments=[],
            incidents=[],
            window=window,
            incident_source_healthy=False,
        )
        assert result.status == MetricStatus.UNDETECTABLE
        assert "Incident source unhealthy" in (result.note or "")


class TestRecoveryTimeLinking:
    """Test auto-linking and edge cases."""

    def test_no_events_when_failed_but_no_resolved_incidents(self):
        """Returns NO_EVENTS when failed deployments exist but none have resolved incidents."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        dep = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            finished_at=datetime(2024, 1, 15, 10, 5, 0),
            commits=[],
        )
        inc = Incident(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="1",
            title="Ongoing outage",
            state="open",  # Not resolved
            severity="critical",
            source="labeled_issue",
            started_at=datetime(2024, 1, 15, 11, 0, 0),
            resolved_at=None,
            deployment_id=dep.id,
            raw_data={},
        )
        # Pass incident_links=None to trigger auto-linking
        result = compute_failed_deployment_recovery_time(
            deployments=[dep],
            incidents=[inc],
            incident_links=None,  # Will be auto-computed
            window=window,
        )
        assert result.status == MetricStatus.NO_EVENTS
        assert "No failed deployments with resolved incidents" in (result.note or "")
        assert result.extra is not None
        assert result.extra.get("failed_deployments_count") == 1
        assert result.extra.get("resolved_count") == 0

    def test_skips_deployments_outside_window(self):
        """Skips failed deployments outside the window."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 15),
            end=datetime(2024, 1, 20),
        )
        dep_in = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="deploy-in",
            environment="production",
            sha="a" * 40,
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 16, 10, 0, 0),
            finished_at=datetime(2024, 1, 16, 10, 5, 0),
            commits=[],
        )
        dep_out = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="deploy-out",
            environment="production",
            sha="b" * 40,
            status=DeploymentStatus.FAILED,
            deployed_at=datetime(2024, 1, 10, 10, 0, 0),  # Before window
            finished_at=datetime(2024, 1, 10, 10, 5, 0),
            commits=[],
        )
        inc = Incident(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="1",
            title="Outage",
            state="resolved",
            severity="critical",
            source="labeled_issue",
            started_at=datetime(2024, 1, 16, 11, 0, 0),
            resolved_at=datetime(2024, 1, 16, 13, 0, 0),
            deployment_id=dep_in.id,
            raw_data={},
        )
        # Only link the in-window deployment
        from dora_platform.domain.models import IncidentDeploymentLink, LinkRule

        link = IncidentDeploymentLink(
            id=uuid4(),
            tenant_id=uuid4(),
            incident_id=inc.id,
            deployment_id=dep_in.id,
            rule_id=LinkRule.R1_EXPLICIT,
            evidence={},
            created_by="system",
            created_at=datetime.now(),
        )
        result = compute_failed_deployment_recovery_time(
            deployments=[dep_in, dep_out],
            incidents=[inc],
            incident_links=[link],
            window=window,
        )
        assert result.status == MetricStatus.OK
        assert result.n == 1  # Only one in window

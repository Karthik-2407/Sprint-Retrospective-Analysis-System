"""Tests for deployment frequency metric using golden dataset."""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dora_platform.domain.models import Deployment, Window
from dora_platform.metrics.contract import MetricStatus
from dora_platform.metrics.deployment_frequency import (
    _count_deploy_days,
    compute_deployment_frequency,
    compute_deployment_frequency_with_days,
)

FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "golden" / "deployment_frequency_golden.json"
)


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


def parse_window(data: dict) -> Window:
    """Parse window from golden fixture format."""
    return Window(
        window_type=data.get("window_type", "rolling_28d"),
        start=datetime.fromisoformat(data["start"]).replace(tzinfo=None),
        end=datetime.fromisoformat(data["end"]).replace(tzinfo=None),
    )


class TestDeploymentFrequencyGolden:
    """Test deployment frequency against golden dataset."""

    @pytest.fixture
    def golden(self):
        return load_golden()

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "normal_case"},
            {"name": "empty_window"},
            {"name": "only_staging"},
            {"name": "failed_deployment_excluded"},
        ],
    )
    def test_golden_cases(self, golden, test_case):
        """Run each golden test case."""
        # Find the test case
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        # Parse inputs
        deployments = [parse_deployment(d) for d in tc["deployments"]]
        window = parse_window(tc["window"])
        expected = tc["expected"]

        # Compute metric
        result = compute_deployment_frequency(deployments, window)

        # Assert
        assert result.metric == expected["metric"]
        assert result.status == MetricStatus(expected["status"])
        assert result.n == expected["n"]
        assert result.unit == expected["unit"]
        assert result.window_start == window.start
        assert result.window_end == window.end

        if expected["value"] is None:
            assert result.value is None
        else:
            assert result.value == expected["value"], (
                f"Expected {expected['value']}, got {result.value}"
            )

        if expected["note"]:
            assert expected["note"] in (result.note or "")


class TestDeploymentFrequencySource:
    """Test deployment frequency source configuration handling."""

    def test_undetectable_when_source_not_configured(self):
        """Returns UNDETECTABLE when source_configured=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_deployment_frequency([], window, source_configured=False)
        assert result.status == MetricStatus.UNDETECTABLE
        assert "No deployment source configured" in (result.note or "")

    def test_undetectable_when_source_unhealthy(self):
        """Returns UNDETECTABLE when source_healthy=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_deployment_frequency([], window, source_healthy=False)
        assert result.status == MetricStatus.UNDETECTABLE
        assert "Deployment source unhealthy" in (result.note or "")


class TestCountDeployDays:
    """Test _count_deploy_days helper."""

    def test_empty_list_returns_zero(self):
        """Returns 0 for empty deployment list."""
        assert _count_deploy_days([]) == 0

    def test_counts_unique_days(self):
        """Counts unique calendar days."""
        dep1 = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="d1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            commits=[],
        )
        dep2 = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="d2",
            environment="production",
            sha="b" * 40,
            status="success",
            deployed_at=datetime(2024, 1, 15, 14, 0, 0),  # Same day
            commits=[],
        )
        dep3 = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="d3",
            environment="production",
            sha="c" * 40,
            status="success",
            deployed_at=datetime(2024, 1, 16, 10, 0, 0),  # Next day
            commits=[],
        )
        assert _count_deploy_days([dep1, dep2, dep3]) == 2


class TestDeploymentFrequencyWithDays:
    """Test compute_deployment_frequency_with_days."""

    def test_ok_status_returns_both_metrics(self):
        """Returns both metrics with OK status when deployments exist."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        dep = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="d1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=datetime(2024, 1, 15, 10, 0, 0),
            commits=[],
        )
        result = compute_deployment_frequency_with_days([dep], window)
        assert result["deployment_frequency"].status == MetricStatus.OK
        assert result["deploy_days"].status == MetricStatus.OK
        assert result["deployment_frequency"].value == 1.0
        assert result["deploy_days"].value == 1.0

    def test_no_events_status_returns_both_no_events(self):
        """Returns NO_EVENTS for both metrics when no deployments."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_deployment_frequency_with_days([], window)
        assert result["deployment_frequency"].status == MetricStatus.NO_EVENTS
        assert result["deploy_days"].status == MetricStatus.NO_EVENTS

    def test_undetectable_returns_both_undetectable(self):
        """Returns UNDETECTABLE for both metrics when source not configured."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_deployment_frequency_with_days([], window, source_configured=False)
        assert result["deployment_frequency"].status == MetricStatus.UNDETECTABLE
        assert result["deploy_days"].status == MetricStatus.UNDETECTABLE

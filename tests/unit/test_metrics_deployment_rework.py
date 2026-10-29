"""Tests for deployment rework metric (PROPOSED) using golden dataset."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from dora_platform.domain.models import Deployment, Window
from dora_platform.metrics.contract import MetricStatus
from dora_platform.metrics.deployment_rework import compute_deployment_rework_rate

FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "golden" / "deployment_rework_golden.json"
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
        raw_data={"is_planned": data.get("is_planned", True)},
    )


def parse_window(data: dict) -> Window:
    """Parse window from golden fixture format."""
    return Window(
        window_type=data.get("window_type", "rolling_28d"),
        start=datetime.fromisoformat(data["start"]).replace(tzinfo=None),
        end=datetime.fromisoformat(data["end"]).replace(tzinfo=None),
    )


class TestDeploymentReworkGolden:
    """Test deployment rework against golden dataset."""

    @pytest.fixture
    def golden(self):
        return load_golden()

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "normal_rework"},
            {"name": "all_planned"},
            {"name": "all_unplanned"},
            {"name": "no_production_deployments"},
            {"name": "empty_window"},
        ],
    )
    def test_golden_cases(self, golden, test_case):
        """Run each golden test case."""
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        deployments = [parse_deployment(d) for d in tc.get("deployments", [])]
        window = parse_window(tc["window"])
        expected = tc["expected"]

        result = compute_deployment_rework_rate(deployments, [], window)

        assert result.metric == expected["metric"]
        assert result.status == MetricStatus(expected["status"])
        assert result.n == expected["n"]
        assert result.unit == expected["unit"]
        assert result.window_start == window.start
        assert result.window_end == window.end

        if expected["value"] is None:
            assert result.value is None
        else:
            # Allow small floating point differences
            assert abs(result.value - expected["value"]) < 0.01, (
                f"Expected {expected['value']}, got {result.value}"
            )

        if expected["note"]:
            assert expected["note"] in (result.note or "")

        # Check unplanned/total counts if present
        if "unplanned_count" in expected:
            assert result.extra is not None
            assert result.extra.get("unplanned_count") == expected["unplanned_count"]

        if "total_count" in expected:
            assert result.extra is not None
            assert result.extra.get("total_count") == expected["total_count"]

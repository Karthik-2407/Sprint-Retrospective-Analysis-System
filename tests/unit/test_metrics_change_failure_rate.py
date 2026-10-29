"""Tests for change failure rate metric using golden dataset."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from dora_platform.domain.models import Deployment, Incident, Window
from dora_platform.metrics.change_failure_rate import compute_change_failure_rate
from dora_platform.metrics.contract import MetricStatus

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden" / "cfr_golden.json"


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


def parse_window(data: dict) -> Window:
    """Parse window from golden fixture format."""
    return Window(
        window_type=data.get("window_type", "rolling_28d"),
        start=datetime.fromisoformat(data["start"]).replace(tzinfo=None),
        end=datetime.fromisoformat(data["end"]).replace(tzinfo=None),
    )


class TestCFRGolden:
    """Test change failure rate against golden dataset."""

    @pytest.fixture
    def golden(self):
        return load_golden()

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "r1_explicit_link"},
            {"name": "r2_sha_reference"},
            {"name": "near_miss_no_link"},
            {"name": "incident_source_undetectable"},
            {"name": "no_production_deployments"},
        ],
    )
    def test_golden_cases(self, golden, test_case):
        """Run each golden test case."""
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        deployments = [parse_deployment(d) for d in tc.get("deployments", [])]
        incidents = [parse_incident(i) for i in tc.get("incidents", [])]
        window = parse_window(tc["window"])
        incident_source_configured = tc.get("incident_source_configured", True)
        expected = tc["expected"]

        result = compute_change_failure_rate(
            deployments=deployments,
            incidents=incidents,
            window=window,
            incident_source_configured=incident_source_configured,
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
            # Allow small floating point differences for Wilson CI
            assert abs(result.value - expected["value"]) < 0.01, (
                f"Expected {expected['value']}, got {result.value}"
            )

        if expected["note"]:
            assert expected["note"] in (result.note or "")

        # Check Wilson CI bounds if present
        if "wilson_ci_lower" in expected and expected["wilson_ci_lower"] is not None:
            assert result.extra is not None
            assert "wilson_ci_lower" in result.extra
            assert abs(result.extra["wilson_ci_lower"] - expected["wilson_ci_lower"]) < 0.01

        if "wilson_ci_upper" in expected and expected["wilson_ci_upper"] is not None:
            assert result.extra is not None
            assert "wilson_ci_upper" in result.extra
            assert abs(result.extra["wilson_ci_upper"] - expected["wilson_ci_upper"]) < 0.01

        # Check failed/total counts if present
        if "failed_count" in expected:
            assert result.extra is not None
            assert result.extra.get("failed_count") == expected["failed_count"]

        if "total_count" in expected:
            assert result.extra is not None
            assert result.extra.get("total_count") == expected["total_count"]

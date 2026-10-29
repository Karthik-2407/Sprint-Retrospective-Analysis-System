"""Tests for lead time metric using golden dataset."""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dora_platform.domain.models import Commit, Deployment, PullRequest, Window
from dora_platform.metrics.contract import MetricStatus
from dora_platform.metrics.lead_time import (
    compute_both_lead_times,
    compute_lead_time,
    compute_lead_time_commit_to_deploy,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden" / "lead_time_golden.json"


def load_golden():
    """Load golden dataset."""
    with FIXTURE_PATH.open() as f:
        return json.load(f)


def parse_commit(data: dict) -> Commit:
    """Parse commit from golden fixture format."""
    return Commit(
        sha=data["sha"],
        repository_id=data["repository_id"],
        authored_at=datetime.fromisoformat(data["authored_at"]).replace(tzinfo=None),
        message=data["message"],
    )


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
        commits=[parse_commit(c) for c in data.get("commits", [])],
    )


def parse_pr(data: dict) -> PullRequest:
    """Parse PR from golden fixture format."""
    return PullRequest(
        id=data["id"],
        repository_id=data["repository_id"],
        provider=data["provider"],
        external_id=data["external_id"],
        title=data["title"],
        state=data["state"],
        merge_method=data.get("merge_method"),
        merge_commit_sha=data.get("merge_commit_sha"),
        base_branch=data.get("base_branch"),
        head_branch=data.get("head_branch"),
        opened_at=datetime.fromisoformat(data["opened_at"]).replace(tzinfo=None),
        merged_at=(
            datetime.fromisoformat(data["merged_at"]).replace(tzinfo=None)
            if data.get("merged_at")
            else None
        ),
        closed_at=(
            datetime.fromisoformat(data["closed_at"]).replace(tzinfo=None)
            if data.get("closed_at")
            else None
        ),
        commits=[parse_commit(c) for c in data.get("commits", [])],
    )


def parse_window(data: dict) -> Window:
    """Parse window from golden fixture format."""
    return Window(
        window_type=data.get("window_type", "rolling_28d"),
        start=datetime.fromisoformat(data["start"]).replace(tzinfo=None),
        end=datetime.fromisoformat(data["end"]).replace(tzinfo=None),
    )


class TestLeadTimeGolden:
    """Test lead time against golden dataset."""

    @pytest.fixture
    def golden(self):
        return load_golden()

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "normal_merge_to_deploy"},
            {"name": "pending_pr_not_deployed"},
            {"name": "multiple_prs_mixed"},
        ],
    )
    def test_golden_cases_primary(self, golden, test_case):
        """Run each golden test case for primary metric (PR merge -> deploy)."""
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        prs = [parse_pr(p) for p in tc.get("prs", [])]
        deployments = [parse_deployment(d) for d in tc.get("deployments", [])]
        window = parse_window(tc["window"])
        expected = tc["expected_primary"]

        result = compute_lead_time(prs, deployments, window)

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

    @pytest.mark.parametrize(
        "test_case",
        [
            {"name": "normal_merge_to_deploy"},
            {"name": "pending_pr_not_deployed"},
            {"name": "multiple_prs_mixed"},
        ],
    )
    def test_golden_cases_secondary(self, golden, test_case):
        """Run each golden test case for secondary metric (commit -> deploy)."""
        tc = next(t for t in golden["test_cases"] if t["name"] == test_case["name"])

        prs = [parse_pr(p) for p in tc.get("prs", [])]
        deployments = [parse_deployment(d) for d in tc.get("deployments", [])]
        window = parse_window(tc["window"])
        expected = tc["expected_secondary"]

        result = compute_lead_time_commit_to_deploy(prs, deployments, window)

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


class TestLeadTimeSource:
    """Test lead time source configuration handling."""

    def test_undetectable_when_source_not_configured(self):
        """Returns UNDETECTABLE when source_configured=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_lead_time([], [], window, source_configured=False)
        assert result.status == MetricStatus.UNDETECTABLE
        assert "No PR/deployment source configured" in (result.note or "")

    def test_undetectable_when_source_unhealthy(self):
        """Returns UNDETECTABLE when source_healthy=False."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        result = compute_lead_time([], [], window, source_healthy=False)
        assert result.status == MetricStatus.UNDETECTABLE
        assert "PR/deployment source unhealthy" in (result.note or "")

    def test_no_events_when_no_prs_in_window(self):
        """Returns NO_EVENTS when no merged PRs in window."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        pr = PullRequest(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="1",
            title="Old PR",
            state="merged",
            merge_method="merge",
            merge_commit_sha="a" * 40,
            base_branch="main",
            head_branch="feature",
            opened_at=datetime(2023, 12, 1),
            merged_at=datetime(2023, 12, 15),  # Before window
            closed_at=datetime(2023, 12, 15),
            commits=[],
        )
        result = compute_lead_time([pr], [], window)
        assert result.status == MetricStatus.NO_EVENTS
        assert "No merged PRs in window" in (result.note or "")

    def test_no_events_when_all_prs_pending(self):
        """Returns NO_EVENTS when all merged PRs are pending deployment."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        pr = PullRequest(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="1",
            title="Pending PR",
            state="merged",
            merge_method="merge",
            merge_commit_sha="a" * 40,
            base_branch="main",
            head_branch="feature",
            opened_at=datetime(2024, 1, 10),
            merged_at=datetime(2024, 1, 15),
            closed_at=datetime(2024, 1, 15),
            commits=[],
        )
        result = compute_lead_time([pr], [], window)
        assert result.status == MetricStatus.NO_EVENTS
        assert "pending deployment" in (result.note or "")
        assert result.extra is not None
        assert "pending_prs" in result.extra

    def test_compute_both_lead_times(self):
        """Test compute_both_lead_times returns both metrics."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )
        pr = PullRequest(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="1",
            title="Test PR",
            state="merged",
            merge_method="merge",
            merge_commit_sha="a" * 40,
            base_branch="main",
            head_branch="feature",
            opened_at=datetime(2024, 1, 10),
            merged_at=datetime(2024, 1, 15),
            closed_at=datetime(2024, 1, 15),
            commits=[
                Commit(
                    sha="a" * 40,
                    repository_id=uuid4(),
                    authored_at=datetime(2024, 1, 10, 9, 30, 0),
                    message="Initial commit",
                )
            ],
        )
        dep = Deployment(
            id=uuid4(),
            repository_id=uuid4(),
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=datetime(2024, 1, 16, 10, 0, 0),
            finished_at=datetime(2024, 1, 16, 10, 5, 0),
            commits=[pr.commits[0]],
        )
        result = compute_both_lead_times([pr], [dep], window)
        assert "lead_time" in result
        assert "lead_time_commit_to_deploy" in result
        assert result["lead_time"].status == MetricStatus.OK
        assert result["lead_time_commit_to_deploy"].status == MetricStatus.OK

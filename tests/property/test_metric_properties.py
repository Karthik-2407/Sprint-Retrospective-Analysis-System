"""Property-based tests for metric engine using Hypothesis.

Tests:
- Order independence: shuffling events yields same result
- Idempotence: re-ingesting same events yields same snapshots
- Monotonic windows: larger window contains smaller window's events
- N/A propagation: UNDETECTABLE + OK = UNDETECTABLE
- Never returns 0 for undetectable/missing data
"""

from datetime import datetime, timedelta
from uuid import uuid4

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from dora_platform.domain.models import Commit, Deployment, Incident, PullRequest, Window
from dora_platform.linking.rules import compute_links
from dora_platform.metrics.change_failure_rate import compute_change_failure_rate
from dora_platform.metrics.contract import MetricStatus
from dora_platform.metrics.deployment_frequency import compute_deployment_frequency
from dora_platform.metrics.deployment_rework import compute_deployment_rework_rate
from dora_platform.metrics.failed_deployment_recovery import compute_failed_deployment_recovery_time
from dora_platform.metrics.lead_time import compute_lead_time
from dora_platform.stats.intervals import wilson_score_interval
from dora_platform.stats.spearman import spearman_rho

# --- Hypothesis Strategies ---


@composite
def deployment_strategy(draw):
    """Generate a valid deployment."""
    return Deployment(
        id=uuid4(),
        repository_id=uuid4(),
        provider="github",
        external_id=draw(st.text(min_size=1, max_size=20)),
        environment=draw(st.sampled_from(["production", "staging", "development"])),
        sha=draw(st.from_regex(r"[0-9a-f]{40}", fullmatch=True)),
        status=draw(st.sampled_from(["success", "failed", "pending"])),
        deployed_at=draw(
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
        ),
        finished_at=draw(
            st.one_of(
                st.none(),
                st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
            )
        ),
        commits=[],
    )


@composite
def commit_strategy(draw):
    """Generate a valid commit."""
    return Commit(
        sha=draw(st.from_regex(r"[0-9a-f]{40}", fullmatch=True)),
        repository_id=uuid4(),
        authored_at=draw(
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
        ),
        message=draw(st.text(min_size=1, max_size=100)),
    )


@composite
def pr_strategy(draw, commits=None):
    """Generate a valid pull request."""
    if commits is None:
        commits = draw(st.lists(commit_strategy(), min_size=1, max_size=5))

    merge_commit_sha = draw(st.one_of(st.none(), st.from_regex(r"[0-9a-f]{40}", fullmatch=True)))
    return PullRequest(
        id=uuid4(),
        repository_id=uuid4(),
        provider="github",
        external_id=draw(st.text(min_size=1, max_size=20)),
        title=draw(st.text(min_size=1, max_size=100)),
        state=draw(st.sampled_from(["open", "merged", "closed"])),
        merge_method=draw(st.one_of(st.none(), st.sampled_from(["merge", "squash", "rebase"]))),
        merge_commit_sha=merge_commit_sha,
        base_branch=draw(st.sampled_from(["main", "master", "develop"])),
        head_branch=draw(st.text(min_size=1, max_size=30)),
        opened_at=draw(
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
        ),
        merged_at=draw(
            st.one_of(
                st.none(),
                st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
            )
        ),
        closed_at=draw(
            st.one_of(
                st.none(),
                st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
            )
        ),
        commits=commits,
    )


@composite
def incident_strategy(draw):
    """Generate a valid incident."""
    return Incident(
        id=uuid4(),
        repository_id=uuid4(),
        provider="github",
        external_id=draw(st.text(min_size=1, max_size=20)),
        title=draw(st.text(min_size=1, max_size=100)),
        state=draw(st.sampled_from(["open", "resolved", "closed"])),
        severity=draw(st.one_of(st.none(), st.sampled_from(["critical", "high", "medium", "low"]))),
        source=draw(
            st.one_of(st.none(), st.sampled_from(["labeled_issue", "pagerduty", "datadog"]))
        ),
        started_at=draw(
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
        ),
        resolved_at=draw(
            st.one_of(
                st.none(),
                st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
            )
        ),
        deployment_id=draw(st.one_of(st.none(), st.uuids())),
        raw_data={},
    )


@composite
def window_strategy(draw):
    """Generate a valid window."""
    start = draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1)))
    end = start + timedelta(days=draw(st.integers(1, 365)))
    return Window(
        window_type=draw(
            st.sampled_from(["rolling_28d", "rolling_90d", "calendar_week", "calendar_month"])
        ),
        start=start,
        end=end,
    )


# --- Test Classes ---


class TestOrderIndependence:
    """Tests for order independence of metric computations."""

    @given(
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=10),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_deployment_frequency_order_independence(self, deployments, window):
        """Deployment frequency should be independent of input order."""
        # Shuffle deployments
        shuffled = deployments[:]
        np.random.shuffle(shuffled)

        result1 = compute_deployment_frequency(deployments, window)
        result2 = compute_deployment_frequency(shuffled, window)

        assert result1.value == result2.value
        assert result1.status == result2.status
        assert result1.n == result2.n

    @given(
        prs=st.lists(pr_strategy(), min_size=1, max_size=5),
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=5),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_lead_time_order_independence(self, prs, deployments, window):
        """Lead time should be independent of input order."""
        shuffled_prs = prs[:]
        np.random.shuffle(shuffled_prs)
        shuffled_deps = deployments[:]
        np.random.shuffle(shuffled_deps)

        result1 = compute_lead_time(prs, deployments, window)
        result2 = compute_lead_time(shuffled_prs, shuffled_deps, window)

        assert result1.value == result2.value
        assert result1.status == result2.status
        assert result1.n == result2.n

    @given(
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=5),
        incidents=st.lists(incident_strategy(), min_size=1, max_size=5),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_cfr_order_independence(self, deployments, incidents, window):
        """CFR should be independent of input order."""
        shuffled_deps = deployments[:]
        np.random.shuffle(shuffled_deps)
        shuffled_incs = incidents[:]
        np.random.shuffle(shuffled_incs)

        result1 = compute_change_failure_rate(deployments, incidents, window)
        result2 = compute_change_failure_rate(shuffled_deps, shuffled_incs, window)

        assert result1.value == result2.value
        assert result1.status == result2.status
        assert result1.n == result2.n


class TestIdempotence:
    """Tests for idempotence of metric computations."""

    @given(
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=10),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_deployment_frequency_idempotence(self, deployments, window):
        """Running deployment frequency twice should yield identical results."""
        result1 = compute_deployment_frequency(deployments, window)
        result2 = compute_deployment_frequency(deployments, window)

        assert result1.value == result2.value
        assert result1.status == result2.status
        assert result1.n == result2.n
        assert result1.evidence_ids == result2.evidence_ids
        assert result1.definition_version == result2.definition_version

    @given(
        prs=st.lists(pr_strategy(), min_size=1, max_size=5),
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=5),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_lead_time_idempotence(self, prs, deployments, window):
        """Running lead time twice should yield identical results."""
        result1 = compute_lead_time(prs, deployments, window)
        result2 = compute_lead_time(prs, deployments, window)

        assert result1.value == result2.value
        assert result1.status == result2.status
        assert result1.n == result2.n
        assert result1.extra == result2.extra


class TestMonotonicWindows:
    """Tests for monotonic window property."""

    @given(
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=10),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_deployment_frequency_monotonic_windows(self, deployments, window):
        """Larger window should contain all events of smaller window."""
        # Create a smaller window within the original
        small_start = window.start + timedelta(days=1)
        small_end = window.end - timedelta(days=1)

        if small_start >= small_end:
            return  # Skip if window too small

        small_window = Window(
            window_type=window.window_type,
            start=small_start,
            end=small_end,
        )

        result_large = compute_deployment_frequency(deployments, window)
        result_small = compute_deployment_frequency(deployments, small_window)

        # Both should have same status if both have events
        if result_large.status == MetricStatus.OK and result_small.status == MetricStatus.OK:
            assert result_small.n <= result_large.n


class TestNAPropagation:
    """Tests for N/A status propagation."""

    def test_undetectable_plus_ok_is_undetectable(self):
        """UNDETECTABLE status should propagate when combined with OK."""
        # This is more of a contract test - metrics should never return 0 for UNDETECTABLE
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )

        # Source not configured -> UNDETECTABLE
        result = compute_deployment_frequency([], window, source_configured=False)
        assert result.status == MetricStatus.UNDETECTABLE
        assert result.value is None  # Never 0!

        # Same for other metrics
        result_lt = compute_lead_time([], [], window, source_configured=False)
        assert result_lt.status == MetricStatus.UNDETECTABLE
        assert result_lt.value is None

        result_cfr = compute_change_failure_rate([], [], window, incident_source_configured=False)
        assert result_cfr.status == MetricStatus.UNDETECTABLE
        assert result_cfr.value is None

        result_rec = compute_failed_deployment_recovery_time(
            [], [], [], window, deployment_source_configured=False
        )
        assert result_rec.status == MetricStatus.UNDETECTABLE
        assert result_rec.value is None

        result_rework = compute_deployment_rework_rate([], [], window, source_configured=False)
        assert result_rework.status == MetricStatus.UNDETECTABLE
        assert result_rework.value is None

    def test_no_events_not_zero(self):
        """NO_EVENTS should never return 0 as value."""
        window = Window(
            window_type="rolling_28d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 28),
        )

        # No deployments -> NO_EVENTS
        result = compute_deployment_frequency([], window)
        assert result.status == MetricStatus.NO_EVENTS
        assert result.value is None  # Not 0!

        # No PRs in window -> NO_EVENTS
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
            opened_at=datetime(2023, 1, 1),
            merged_at=datetime(2023, 1, 15),
            closed_at=datetime(2023, 1, 15),
            commits=[],
        )
        result_lt = compute_lead_time([pr], [], window)
        assert result_lt.status == MetricStatus.NO_EVENTS
        assert result_lt.value is None  # Not 0!


class TestLinkingProperties:
    """Tests for linking rule properties."""

    @given(
        incident=incident_strategy(),
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_linking_deterministic(self, incident, deployments):
        """Linking should be deterministic - same inputs always produce same links."""
        links1 = compute_links(incident, deployments)
        links2 = compute_links(incident, deployments)

        assert len(links1) == len(links2)
        for l1, l2 in zip(links1, links2, strict=False):
            assert l1.rule_id == l2.rule_id
            assert l1.deployment_id == l2.deployment_id
            assert l1.evidence == l2.evidence

    @given(
        incident=incident_strategy(),
        deployments=st.lists(deployment_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_linking_priority_r1_over_r2(self, incident, deployments):
        """R1 should take priority over R2 when both match."""
        # Create new incident with explicit deployment_id AND SHA in body
        incident = Incident(
            id=incident.id,
            repository_id=incident.repository_id,
            provider=incident.provider,
            external_id=incident.external_id,
            title=incident.title,
            state=incident.state,
            severity=incident.severity,
            source=incident.source,
            started_at=incident.started_at,
            resolved_at=incident.resolved_at,
            deployment_id=deployments[0].id,
            raw_data={"body": f"caused by {deployments[0].sha}"},
        )

        links = compute_links(incident, deployments)

        # Should only have R1 link
        assert len(links) == 1
        assert links[0].rule_id == "R1"


class TestStatisticalProperties:
    """Tests for statistical function properties."""

    @given(
        x=st.lists(
            st.floats(min_value=-100, max_value=100, allow_nan=False), min_size=30, max_size=100
        ).filter(lambda arr: len(set(arr)) > 1),
        y=st.lists(
            st.floats(min_value=-100, max_value=100, allow_nan=False), min_size=30, max_size=100
        ).filter(lambda arr: len(set(arr)) > 1),
    )
    @settings(max_examples=20)
    def test_spearman_rho_symmetric(self, x, y):
        """Spearman correlation should be symmetric."""
        # Make sure they're same length
        min_len = min(len(x), len(y))
        x = x[:min_len]
        y = y[:min_len]

        if len(x) < 30:
            return

        result_xy = spearman_rho(x, y, min_n=30)
        result_yx = spearman_rho(y, x, min_n=30)

        assert abs(result_xy.rho - result_yx.rho) < 1e-10
        assert result_xy.n == result_yx.n

    @given(
        x=st.lists(
            st.floats(min_value=0, max_value=1, allow_nan=False), min_size=30, max_size=100
        ).filter(lambda arr: len(set(arr)) > 1),
    )
    @settings(max_examples=20)
    def test_spearman_rho_perfect_positive(self, x):
        """Perfect positive correlation should give rho=1."""
        result = spearman_rho(x, x, min_n=30)
        assert abs(result.rho - 1.0) < 1e-10

    @given(
        successes=st.integers(0, 100),
        trials=st.integers(1, 100),
    )
    @settings(max_examples=50)
    def test_wilson_interval_bounds(self, successes, trials):
        """Wilson interval should always be within [0, 1]."""
        if successes > trials:
            return

        ci = wilson_score_interval(successes, trials, confidence=0.95)
        assert 0 <= ci.lower <= 1
        assert 0 <= ci.upper <= 1
        assert ci.lower <= ci.upper

    @given(
        successes=st.integers(0, 1000),
        trials=st.integers(1, 1000),
    )
    @settings(max_examples=50)
    def test_wilson_percentage_bounds(self, successes, trials):
        """Wilson percentage interval should be within [0, 100]."""
        if successes > trials:
            return

        from dora_platform.stats.intervals import wilson_score_interval_percentage

        ci = wilson_score_interval_percentage(successes, trials, confidence=0.95)
        assert 0 <= ci.lower <= 100
        assert 0 <= ci.upper <= 100
        assert ci.lower <= ci.upper


class TestMetricContract:
    """Tests for MetricValue contract compliance."""

    @given(
        deployments=st.lists(deployment_strategy(), min_size=0, max_size=5),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_metric_value_always_has_required_fields(self, deployments, window):
        """Every MetricValue should have all required fields."""
        result = compute_deployment_frequency(deployments, window)

        # Required fields
        assert isinstance(result.metric, str)
        assert result.metric == "deployment_frequency"
        assert result.unit == "count"
        assert isinstance(result.status, MetricStatus)
        assert isinstance(result.n, int)
        assert result.n >= 0
        assert isinstance(result.window_start, datetime)
        assert isinstance(result.window_end, datetime)
        assert isinstance(result.definition_version, str)
        assert result.definition_version.startswith("ADR-")

        # Status-specific invariants
        if result.status in (MetricStatus.UNDETECTABLE, MetricStatus.NO_EVENTS):
            assert result.value is None
            assert result.n == 0
        elif result.status == MetricStatus.OK:
            assert result.value is not None
            assert isinstance(result.value, (int, float))
            assert result.n > 0

    @given(
        prs=st.lists(pr_strategy(), min_size=0, max_size=3),
        deployments=st.lists(deployment_strategy(), min_size=0, max_size=3),
        window=window_strategy(),
    )
    @settings(max_examples=50)
    def test_lead_time_contract(self, prs, deployments, window):
        """Lead time metric should follow contract."""
        result = compute_lead_time(prs, deployments, window)

        assert result.metric == "lead_time"
        assert result.unit == "seconds"
        assert isinstance(result.status, MetricStatus)
        assert isinstance(result.n, int)
        assert result.n >= 0

        if result.status in (MetricStatus.UNDETECTABLE, MetricStatus.NO_EVENTS):
            assert result.value is None
        elif result.status == MetricStatus.OK:
            assert result.value is not None
            assert result.value >= 0  # Lead time cannot be negative
            assert result.n > 0
            assert "p75" in result.extra
            assert "p90" in result.extra


# Run with: pytest tests/property/test_metric_properties.py -v

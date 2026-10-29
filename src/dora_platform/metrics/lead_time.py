"""Lead time for changes metric.

Per CLAUDE.md §3.1:
- Primary: PR merge → deploy (PR merge to first successful production
  deployment containing the PR's merge commit)
- Secondary (always labeled): commit → deploy (first commit in PR → deploy)
- Aggregate with median, p75, p90 (never mean; durations are skewed) and show n
- PRs merged but not yet deployed are listed as pending and excluded from distribution
- Handle squash, rebase, and merge-commit strategies
"""

from datetime import datetime

import numpy as np

from dora_platform.domain.models import Deployment, PullRequest, Window
from dora_platform.metrics.contract import MetricStatus, MetricValue

DEFINITION_VERSION_PRIMARY = "ADR-0002@1"  # PR merge → deploy
DEFINITION_VERSION_SECONDARY = "ADR-0002@1-secondary"  # commit → deploy


def _find_deployment_for_pr(
    pr: PullRequest,
    deployments: list[Deployment],
) -> Deployment | None:
    """Find the first successful production deployment containing the PR's merge commit.

    For squash merges: look for the merge_commit_sha
    For merge commits: look for the merge_commit_sha
    For rebase: look for the individual commits in the PR
    """
    if not pr.is_merged or pr.merged_at is None:
        return None

    # Filter to successful production deployments after PR merge
    candidate_deploys = [
        d
        for d in deployments
        if d.is_production
        and d.is_successful
        and d.deployed_at is not None
        and d.deployed_at >= pr.merged_at
    ]

    if not candidate_deploys:
        return None

    # Sort by deployed_at to find the first one
    # All items have deployed_at is not None due to filter above
    from datetime import datetime as dt_datetime

    candidate_deploys.sort(key=lambda d: d.deployed_at or dt_datetime.min)

    # Get the commit SHAs that represent this PR
    pr_shas = set()
    if pr.merge_commit_sha:
        pr_shas.add(pr.merge_commit_sha.lower())
    for commit in pr.commits:
        pr_shas.add(commit.sha.lower())

    # Find first deployment that contains any of the PR's commits
    for dep in candidate_deploys:
        dep_shas = {c.sha.lower() for c in dep.commits}
        if pr_shas & dep_shas:  # Intersection non-empty
            return dep

    return None


def _compute_lead_times(
    prs: list[PullRequest],
    deployments: list[Deployment],
    use_merge_time: bool = True,  # True = PR merge → deploy, False = first commit → deploy
) -> list[float]:
    """Compute lead times in seconds for all merged PRs that have been deployed."""
    lead_times = []

    for pr in prs:
        if not pr.is_merged:
            continue

        dep = _find_deployment_for_pr(pr, deployments)
        if dep is None or dep.deployed_at is None:
            continue  # Not yet deployed (pending)

        if use_merge_time and pr.merged_at is not None:
            start = pr.merged_at
        elif not use_merge_time and pr.commits:
            # Use earliest commit in PR
            commit_times = [c.authored_at for c in pr.commits if c.authored_at is not None]
            if not commit_times:
                continue
            start = min(commit_times)
        else:
            continue

        lead_time_seconds = (dep.deployed_at - start).total_seconds()
        if lead_time_seconds >= 0:
            lead_times.append(lead_time_seconds)

    return lead_times


def compute_lead_time(
    prs: list[PullRequest],
    deployments: list[Deployment],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> MetricValue:
    """Compute lead time for changes (primary: PR merge → deploy)."""
    return _compute_lead_time_metric(
        prs=prs,
        deployments=deployments,
        window=window,
        now=now,
        source_configured=source_configured,
        source_healthy=source_healthy,
        use_merge_time=True,
        definition_version=DEFINITION_VERSION_PRIMARY,
        metric_name="lead_time",
    )


def compute_lead_time_commit_to_deploy(
    prs: list[PullRequest],
    deployments: list[Deployment],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> MetricValue:
    """Compute lead time for changes (secondary: commit → deploy).

    Always labeled as "commit-to-deploy (DORA reference definition)".
    """
    return _compute_lead_time_metric(
        prs=prs,
        deployments=deployments,
        window=window,
        now=now,
        source_configured=source_configured,
        source_healthy=source_healthy,
        use_merge_time=False,
        definition_version=DEFINITION_VERSION_SECONDARY,
        metric_name="lead_time_commit_to_deploy",
    )


def _compute_lead_time_metric(
    prs: list[PullRequest],
    deployments: list[Deployment],
    window: Window,
    now: datetime | None,
    source_configured: bool,
    source_healthy: bool,
    use_merge_time: bool,
    definition_version: str,
    metric_name: str,
) -> MetricValue:
    """Internal function to compute lead time metric."""
    if not source_configured:
        return MetricValue(
            metric=metric_name,
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=definition_version,
            note="No PR/deployment source configured",
        )

    if not source_healthy:
        return MetricValue(
            metric=metric_name,
            value=None,
            unit="seconds",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=definition_version,
            note="PR/deployment source unhealthy",
        )

    # Filter PRs merged within the window
    prs_in_window = [
        pr
        for pr in prs
        if pr.is_merged and pr.merged_at is not None and window.start <= pr.merged_at < window.end
    ]

    if not prs_in_window:
        return MetricValue(
            metric=metric_name,
            value=None,
            unit="seconds",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=definition_version,
            note="No merged PRs in window",
        )

    # Compute lead times
    lead_times = _compute_lead_times(prs_in_window, deployments, use_merge_time)

    # Find pending PRs (merged but not deployed)
    pending_prs = []
    for pr in prs_in_window:
        dep = _find_deployment_for_pr(pr, deployments)
        if dep is None:
            pending_prs.append(str(pr.id))

    deployed_count = len(lead_times)

    if deployed_count == 0:
        # All PRs are pending
        return MetricValue(
            metric=metric_name,
            value=None,
            unit="seconds",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window.start,
            window_end=window.end,
            definition_version=definition_version,
            note=f"All {len(prs_in_window)} merged PRs pending deployment",
            extra={"pending_prs": pending_prs, "total_merged": len(prs_in_window)},
        )

    # Compute statistics
    lead_times_arr = np.array(lead_times)
    median_lt = float(np.median(lead_times_arr))
    p75_lt = float(np.percentile(lead_times_arr, 75))
    p90_lt = float(np.percentile(lead_times_arr, 90))

    # Evidence IDs are the PR IDs that were deployed
    deployed_pr_ids = tuple(
        str(pr.id) for pr in prs_in_window if _find_deployment_for_pr(pr, deployments) is not None
    )

    return MetricValue(
        metric=metric_name,
        value=median_lt,
        unit="seconds",
        status=MetricStatus.OK,
        n=deployed_count,
        window_start=window.start,
        window_end=window.end,
        definition_version=definition_version,
        evidence_ids=deployed_pr_ids,
        extra={
            "p75": p75_lt,
            "p90": p90_lt,
            "pending_prs": pending_prs,
            "total_merged": len(prs_in_window),
        },
    )


def compute_both_lead_times(
    prs: list[PullRequest],
    deployments: list[Deployment],
    window: Window,
    now: datetime | None = None,
    source_configured: bool = True,
    source_healthy: bool = True,
) -> dict[str, MetricValue]:
    """Compute both primary and secondary lead time metrics."""
    return {
        "lead_time": compute_lead_time(
            prs, deployments, window, now, source_configured, source_healthy
        ),
        "lead_time_commit_to_deploy": compute_lead_time_commit_to_deploy(
            prs, deployments, window, now, source_configured, source_healthy
        ),
    }

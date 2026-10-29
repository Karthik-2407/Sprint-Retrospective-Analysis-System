"""Metric contract — the single return type for all metric computations.

Per §3.3 of CLAUDE.md: every metric function returns this, never a bare number.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class MetricStatus(StrEnum):
    """Status of a metric computation."""

    OK = "ok"  # computed from detectable data (value may legitimately be 0)
    NO_EVENTS = "no_events"  # source healthy, but the population is empty in this window
    UNDETECTABLE = "undetectable"  # required event source missing or unhealthy -> N/A
    INSUFFICIENT_SAMPLE = "insufficient_sample"  # below the minimum n for inferential output
    PARTIAL_DATA = "partial_data"  # computed, but known gaps (backfill incomplete, ingestion lag)


@dataclass(frozen=True, slots=True)
class MetricValue:
    """Versioned, immutable metric result with evidence references.

    Rules (per CLAUDE.md §3.3):
    - value is None whenever status is NO_EVENTS, UNDETECTABLE, or INSUFFICIENT_SAMPLE
    - Aggregations propagate non-OK statuses; a mean/median of "N/A" is N/A, not 0
    - UI and Grafana render each status distinctly (hatched or grey, with tooltip)
    - Changing a definition bumps definition_version and recomputes snapshots
    """

    metric: str  # e.g., "deployment_frequency", "lead_time", "change_failure_rate"
    value: float | None  # None unless status in (OK, PARTIAL_DATA)
    unit: str  # e.g., "count", "seconds", "percentage"
    status: MetricStatus
    n: int  # sample size behind the value
    window_start: datetime
    window_end: datetime
    definition_version: str  # e.g., "ADR-0003@2"; ties result to the written definition
    evidence_ids: tuple[str, ...] = ()  # rows that produced it (drill-down)
    note: str | None = None
    extra: dict[str, Any] = None  # type: ignore[assignment]  # for metric-specific extras

    def __post_init__(self) -> None:
        if self.extra is None:
            object.__setattr__(self, "extra", {})

    def is_ok(self) -> bool:
        """Return True if the metric has a valid computed value."""
        return self.status in (MetricStatus.OK, MetricStatus.PARTIAL_DATA)

    def is_na(self) -> bool:
        """Return True if the metric is not available (should not be shown as a number)."""
        return self.status in (
            MetricStatus.NO_EVENTS,
            MetricStatus.UNDETECTABLE,
            MetricStatus.INSUFFICIENT_SAMPLE,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API/serialization."""
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "n": self.n,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "definition_version": self.definition_version,
            "evidence_ids": list(self.evidence_ids),
            "note": self.note,
            "extra": self.extra or {},
        }

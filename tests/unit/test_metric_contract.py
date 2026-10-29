"""Tests for metric contract types (MetricValue, MetricStatus)."""

from datetime import datetime

import pytest

from dora_platform.metrics.contract import MetricStatus, MetricValue


class TestMetricStatus:
    """Tests for MetricStatus enum."""

    def test_all_statuses_exist(self):
        """All required statuses are present."""
        assert MetricStatus.OK == "ok"
        assert MetricStatus.NO_EVENTS == "no_events"
        assert MetricStatus.UNDETECTABLE == "undetectable"
        assert MetricStatus.INSUFFICIENT_SAMPLE == "insufficient_sample"
        assert MetricStatus.PARTIAL_DATA == "partial_data"

    def test_str_enum_behavior(self):
        """MetricStatus behaves as StrEnum."""
        assert str(MetricStatus.OK) == "ok"
        assert MetricStatus.OK == "ok"
        assert "ok" == MetricStatus.OK


class TestMetricValue:
    """Tests for MetricValue dataclass."""

    def test_ok_value_creation(self):
        """Create a valid OK metric value."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="deployment_frequency",
            value=5.0,
            unit="count",
            status=MetricStatus.OK,
            n=5,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
        )

        assert mv.metric == "deployment_frequency"
        assert mv.value == 5.0
        assert mv.unit == "count"
        assert mv.status == MetricStatus.OK
        assert mv.n == 5
        assert mv.definition_version == "ADR-0003@1"

    def test_no_events_value_none(self):
        """NO_EVENTS status must have value=None."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="deployment_frequency",
            value=None,
            unit="count",
            status=MetricStatus.NO_EVENTS,
            n=0,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
            note="No production deployments in window",
        )

        assert mv.status == MetricStatus.NO_EVENTS
        assert mv.value is None
        assert mv.n == 0
        assert "No production deployments" in mv.note

    def test_undetectable_value_none(self):
        """UNDETECTABLE status must have value=None."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="change_failure_rate",
            value=None,
            unit="percentage",
            status=MetricStatus.UNDETECTABLE,
            n=0,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
            note="No incident source configured",
        )

        assert mv.status == MetricStatus.UNDETECTABLE
        assert mv.value is None

    def test_insufficient_sample_value_none(self):
        """INSUFFICIENT_SAMPLE status must have value=None."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="lead_time_correlation",
            value=None,
            unit="rho",
            status=MetricStatus.INSUFFICIENT_SAMPLE,
            n=15,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
            note="Need n >= 30 for Spearman correlation",
        )

        assert mv.status == MetricStatus.INSUFFICIENT_SAMPLE
        assert mv.value is None
        assert mv.n == 15

    def test_partial_data_has_value(self):
        """PARTIAL_DATA can have a value but with caveat."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="deployment_frequency",
            value=3.0,
            unit="count",
            status=MetricStatus.PARTIAL_DATA,
            n=3,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
            note="Partial week - data collection incomplete",
        )

        assert mv.status == MetricStatus.PARTIAL_DATA
        assert mv.value == 3.0
        assert mv.n == 3

    def test_evidence_ids_optional(self):
        """evidence_ids is optional tuple."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="lead_time",
            value=86400.0,
            unit="seconds",
            status=MetricStatus.OK,
            n=1,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0002@1",
            evidence_ids=("pr-123",),
        )

        assert mv.evidence_ids == ("pr-123",)

    def test_extra_dict_optional(self):
        """extra field is optional dict for additional metadata."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="change_failure_rate",
            value=25.0,
            unit="percentage",
            status=MetricStatus.OK,
            n=20,
            window_start=window_start,
            window_end=window_end,
            definition_version="ADR-0003@1",
            extra={"wilson_ci_lower": 12.5, "wilson_ci_upper": 42.3},
        )

        assert mv.extra["wilson_ci_lower"] == 12.5
        assert mv.extra["wilson_ci_upper"] == 42.3

    def test_frozen_dataclass(self):
        """MetricValue should be immutable (frozen)."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="test",
            value=1.0,
            unit="count",
            status=MetricStatus.OK,
            n=1,
            window_start=window_start,
            window_end=window_end,
            definition_version="v1",
        )

        with pytest.raises(AttributeError):
            mv.value = 2.0

    def test_note_optional(self):
        """note field is optional."""
        window_start = datetime(2024, 1, 14, tzinfo=None)
        window_end = datetime(2024, 1, 20, tzinfo=None)

        mv = MetricValue(
            metric="test",
            value=1.0,
            unit="count",
            status=MetricStatus.OK,
            n=1,
            window_start=window_start,
            window_end=window_end,
            definition_version="v1",
        )

        assert mv.note is None

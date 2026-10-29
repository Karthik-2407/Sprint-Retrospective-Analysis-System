"""Metrics package — all five DORA metrics.

Exports metric computation functions and a registry for easy access.
"""

from dora_platform.metrics.change_failure_rate import compute_change_failure_rate
from dora_platform.metrics.contract import MetricStatus, MetricValue
from dora_platform.metrics.deployment_frequency import (
    compute_deployment_frequency,
    compute_deployment_frequency_with_days,
)
from dora_platform.metrics.deployment_rework import compute_deployment_rework_rate
from dora_platform.metrics.failed_deployment_recovery import compute_failed_deployment_recovery_time
from dora_platform.metrics.lead_time import (
    compute_both_lead_times,
    compute_lead_time,
    compute_lead_time_commit_to_deploy,
)

# Registry mapping metric name -> function
METRIC_REGISTRY = {
    "deployment_frequency": compute_deployment_frequency,
    "lead_time": compute_lead_time,
    "lead_time_commit_to_deploy": compute_lead_time_commit_to_deploy,
    "change_failure_rate": compute_change_failure_rate,
    "failed_deployment_recovery_time": compute_failed_deployment_recovery_time,
    "deployment_rework_rate": compute_deployment_rework_rate,
}

# Metric definition versions (for snapshot versioning)
METRIC_DEFINITION_VERSIONS = {
    "deployment_frequency": "ADR-0001@1",
    "lead_time": "ADR-0002@1",
    "lead_time_commit_to_deploy": "ADR-0002@1-secondary",
    "change_failure_rate": "ADR-0003@1",
    "failed_deployment_recovery_time": "ADR-0003@1",
    "deployment_rework_rate": "ADR-0004@1",
}

__all__ = [
    "MetricStatus",
    "MetricValue",
    "compute_deployment_frequency",
    "compute_deployment_frequency_with_days",
    "compute_lead_time",
    "compute_lead_time_commit_to_deploy",
    "compute_both_lead_times",
    "compute_change_failure_rate",
    "compute_failed_deployment_recovery_time",
    "compute_deployment_rework_rate",
    "METRIC_REGISTRY",
    "METRIC_DEFINITION_VERSIONS",
]

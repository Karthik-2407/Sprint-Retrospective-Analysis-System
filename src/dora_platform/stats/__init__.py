"""Statistics module — Spearman correlation and confidence intervals.

Provides statistical rigor per CLAUDE.md §3.4:
- Spearman's ρ with n ≥ 30 enforcement
- Wilson score interval for CFR
- Bootstrap percentile CIs
"""

from dora_platform.stats.intervals import (
    ConfidenceInterval,
    bootstrap_mean_ci,
    bootstrap_median_ci,
    bootstrap_percentile_ci,
    percentile_ci,
    wilson_score_interval,
    wilson_score_interval_percentage,
)
from dora_platform.stats.spearman import (
    InsufficientSampleError,
    SpearmanResult,
    spearman_matrix,
    spearman_rho,
    spearman_rho_safe,
)

__all__ = [
    "ConfidenceInterval",
    "InsufficientSampleError",
    "SpearmanResult",
    "bootstrap_mean_ci",
    "bootstrap_median_ci",
    "bootstrap_percentile_ci",
    "percentile_ci",
    "spearman_matrix",
    "spearman_rho",
    "spearman_rho_safe",
    "wilson_score_interval",
    "wilson_score_interval_percentage",
]

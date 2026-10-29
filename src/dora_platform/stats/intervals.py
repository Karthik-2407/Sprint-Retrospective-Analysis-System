"""Confidence intervals for metrics.

Includes Wilson score interval for CFR (binomial proportion)
and percentile bootstrap CI for other metrics.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    """Confidence interval with bounds."""

    lower: float
    upper: float
    confidence_level: float  # e.g., 0.95 for 95% CI
    method: str  # e.g., "wilson", "bootstrap_percentile"

    def contains(self, value: float) -> bool:
        """Check if a value falls within the interval."""
        return self.lower <= value <= self.upper

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "confidence_level": self.confidence_level,
            "method": self.method,
        }


def wilson_score_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Wilson score interval for binomial proportion.

    Per CLAUDE.md §3.2: [PROPOSED] Show a Wilson score interval next to
    the CFR rate; at n = 9 a bare percentage is noise.

    The Wilson interval has good coverage properties even for small n
    and extreme proportions (near 0 or 1).

    Args:
        successes: Number of successes (e.g., failed deployments)
        trials: Total number of trials (e.g., total deployments)
        confidence: Confidence level (default 0.95 for 95% CI)

    Returns:
        ConfidenceInterval with lower and upper bounds
    """
    if trials <= 0:
        return ConfidenceInterval(
            lower=0.0,
            upper=0.0,
            confidence_level=confidence,
            method="wilson",
        )

    if successes < 0 or successes > trials:
        raise ValueError(f"Invalid successes={successes} for trials={trials}")

    p = successes / trials
    z = stats.norm.ppf((1 + confidence) / 2)

    # Wilson score interval formula
    denominator = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    half_width = z * np.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator

    lower = max(0.0, centre - half_width)
    upper = min(1.0, centre + half_width)

    return ConfidenceInterval(
        lower=lower,
        upper=upper,
        confidence_level=confidence,
        method="wilson",
    )


def wilson_score_interval_percentage(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Wilson score interval as percentage (0-100)."""
    ci = wilson_score_interval(successes, trials, confidence)
    return ConfidenceInterval(
        lower=ci.lower * 100,
        upper=ci.upper * 100,
        confidence_level=confidence,
        method="wilson_percentage",
    )


def bootstrap_percentile_ci(
    data: list[float] | np.ndarray,
    statistic: Callable[[np.ndarray], float],
    confidence: float = 0.95,
    n_resamples: int = 10000,
    random_state: int | np.random.Generator | None = None,
) -> ConfidenceInterval:
    """Percentile bootstrap confidence interval.

    Args:
        data: Sample data
        statistic: Function that computes the statistic from a sample
        confidence: Confidence level (default 0.95)
        n_resamples: Number of bootstrap resamples
        random_state: Random seed or Generator for reproducibility

    Returns:
        ConfidenceInterval with percentile bounds
    """
    data_arr = np.asarray(data)
    n = len(data_arr)

    if n < 2:
        return ConfidenceInterval(
            lower=float(np.nan),
            upper=float(np.nan),
            confidence_level=confidence,
            method="bootstrap_percentile",
        )

    if random_state is None:
        rng = np.random.default_rng()
    elif isinstance(random_state, int):
        rng = np.random.default_rng(random_state)
    else:
        rng = random_state

    # Compute bootstrap statistics
    boot_stats = np.empty(n_resamples)
    for i in range(n_resamples):
        sample = rng.choice(data_arr, size=n, replace=True)
        boot_stats[i] = statistic(sample)

    # Percentile interval
    alpha = 1 - confidence
    lower_pct = 100 * alpha / 2
    upper_pct = 100 * (1 - alpha / 2)

    lower = float(np.percentile(boot_stats, lower_pct))
    upper = float(np.percentile(boot_stats, upper_pct))

    return ConfidenceInterval(
        lower=lower,
        upper=upper,
        confidence_level=confidence,
        method="bootstrap_percentile",
    )


def bootstrap_median_ci(
    data: list[float] | np.ndarray,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    random_state: int | np.random.Generator | None = None,
) -> ConfidenceInterval:
    """Bootstrap CI for median."""
    return bootstrap_percentile_ci(
        data,
        statistic=np.median,
        confidence=confidence,
        n_resamples=n_resamples,
        random_state=random_state,
    )


def bootstrap_mean_ci(
    data: list[float] | np.ndarray,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    random_state: int | np.random.Generator | None = None,
) -> ConfidenceInterval:
    """Bootstrap CI for mean."""
    return bootstrap_percentile_ci(
        data,
        statistic=np.mean,
        confidence=confidence,
        n_resamples=n_resamples,
        random_state=random_state,
    )


def percentile_ci(
    data: list[float] | np.ndarray,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Direct percentile interval (non-bootstrap) for a sample.

    Useful for computing p50/p90 intervals from a sample directly.
    """
    data_arr = np.asarray(data)
    n = len(data_arr)

    if n == 0:
        return ConfidenceInterval(
            lower=float(np.nan),
            upper=float(np.nan),
            confidence_level=confidence,
            method="percentile",
        )

    alpha = 1 - confidence
    lower_pct = 100 * alpha / 2
    upper_pct = 100 * (1 - alpha / 2)

    lower = float(np.percentile(data_arr, lower_pct))
    upper = float(np.percentile(data_arr, upper_pct))

    return ConfidenceInterval(
        lower=lower,
        upper=upper,
        confidence_level=confidence,
        method="percentile",
    )

"""Spearman rank correlation wrapper with sample-size enforcement.

Per CLAUDE.md §3.4:
- Correlations use Spearman's ρ (rank-based; durations and counts are skewed)
- Report a coefficient only when n ≥ 30 paired observations
- Below that: INSUFFICIENT_SAMPLE and "insufficient data (n = 12)"
- Always show ρ, p-value, n, and the method together
- Implementation: scipy.stats.spearmanr, wrapped with n-threshold enforced inside
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


class InsufficientSampleError(ValueError):
    """Raised when sample size is below the minimum threshold."""

    def __init__(self, n: int, min_n: int) -> None:
        self.n = n
        self.min_n = min_n
        super().__init__(f"Insufficient sample size: n={n}, minimum required: {min_n}")


@dataclass(frozen=True, slots=True)
class SpearmanResult:
    """Result of Spearman correlation computation."""

    rho: float  # Spearman's rank correlation coefficient
    p_value: float  # Two-tailed p-value
    n: int  # Number of paired observations
    method: str = "spearman"  # Method name for reporting

    def is_significant(self, alpha: float = 0.05) -> bool:
        """Return True if correlation is statistically significant at alpha level."""
        return self.p_value < alpha

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API/serialization."""
        return {
            "rho": self.rho,
            "p_value": self.p_value,
            "n": self.n,
            "method": self.method,
            "significant": self.is_significant(),
        }


def spearman_rho(
    x: list[float] | np.ndarray,
    y: list[float] | np.ndarray,
    min_n: int = 30,
    nan_policy: str = "omit",
) -> SpearmanResult:
    """Compute Spearman's rank correlation with sample-size enforcement.

    Args:
        x: First variable (list or array)
        y: Second variable (list or array)
        min_n: Minimum required paired observations (default 30 per CLAUDE.md)
        nan_policy: How to handle NaN values ("omit", "raise", "propagate")

    Returns:
        SpearmanResult with rho, p_value, n, and method

    Raises:
        InsufficientSampleError: If valid paired observations < min_n
        ValueError: If inputs have different lengths or are empty
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    if x_arr.shape != y_arr.shape:
        raise ValueError(f"Input arrays must have same shape: {x_arr.shape} vs {y_arr.shape}")

    if len(x_arr) == 0:
        raise ValueError("Input arrays cannot be empty")

    # Handle NaN values based on policy
    if nan_policy == "omit":
        # Create mask of valid (non-NaN) pairs
        valid_mask = ~(np.isnan(x_arr) | np.isnan(y_arr))
        x_valid = x_arr[valid_mask]
        y_valid = y_arr[valid_mask]
    elif nan_policy == "raise":
        if np.any(np.isnan(x_arr)) or np.any(np.isnan(y_arr)):
            raise ValueError("Input contains NaN values and nan_policy='raise'")
        x_valid = x_arr
        y_valid = y_arr
    else:  # propagate
        x_valid = x_arr
        y_valid = y_arr

    n = len(x_valid)

    if n < min_n:
        raise InsufficientSampleError(n=n, min_n=min_n)

    # Compute Spearman correlation
    result = stats.spearmanr(x_valid, y_valid)

    # Handle scipy return format (can be float or object with .correlation/.pvalue)
    if hasattr(result, "correlation"):
        rho = float(result.correlation)
        p_value = float(result.pvalue)
    else:
        rho = float(result[0])
        p_value = float(result[1])

    return SpearmanResult(rho=rho, p_value=p_value, n=n, method="spearman")


def spearman_rho_safe(
    x: list[float] | np.ndarray,
    y: list[float] | np.ndarray,
    min_n: int = 30,
    nan_policy: str = "omit",
) -> SpearmanResult | None:
    """Safe version that returns None instead of raising InsufficientSampleError.

    Useful for callers that want to handle insufficient sample gracefully.
    """
    try:
        return spearman_rho(x, y, min_n=min_n, nan_policy=nan_policy)
    except InsufficientSampleError:
        return None


def spearman_matrix(
    data: dict[str, list[float] | np.ndarray],
    min_n: int = 30,
    nan_policy: str = "omit",
) -> dict[str, dict[str, SpearmanResult | None]]:
    """Compute pairwise Spearman correlations for multiple variables.

    Args:
        data: Dict mapping variable name -> array of values
        min_n: Minimum required paired observations
        nan_policy: How to handle NaN values

    Returns:
        Nested dict: {var1: {var2: SpearmanResult or None, ...}, ...}
    """
    variables = list(data.keys())
    # Initialize all inner dicts first
    result: dict[str, dict[str, SpearmanResult | None]] = {v: {} for v in variables}

    for i, var1 in enumerate(variables):
        for j, var2 in enumerate(variables):
            if i == j:
                result[var1][var2] = SpearmanResult(rho=1.0, p_value=0.0, n=len(data[var1]))
            elif i < j:
                # Only compute upper triangle, mirror to lower
                corr = spearman_rho_safe(data[var1], data[var2], min_n=min_n, nan_policy=nan_policy)
                result[var1][var2] = corr
                result[var2][var1] = corr
            # else: already computed

    return result

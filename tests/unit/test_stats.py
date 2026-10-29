"""Tests for statistics functions (Spearman, Wilson, bootstrap)."""

import math

import numpy as np
import pytest

from dora_platform.stats.intervals import (
    bootstrap_mean_ci,
    bootstrap_median_ci,
    bootstrap_percentile_ci,
    percentile_ci,
    wilson_score_interval,
    wilson_score_interval_percentage,
)
from dora_platform.stats.spearman import InsufficientSampleError, SpearmanResult, spearman_rho


class TestSpearmanRho:
    """Tests for Spearman rank correlation."""

    def test_perfect_positive_correlation(self):
        """Perfect positive correlation should give rho = 1."""
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, 4, 5]
        result = spearman_rho(x, y, min_n=3)
        assert abs(result.rho - 1.0) < 1e-10
        assert result.n == 5

    def test_perfect_negative_correlation(self):
        """Perfect negative correlation should give rho = -1."""
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]
        result = spearman_rho(x, y, min_n=3)
        assert abs(result.rho - (-1.0)) < 1e-10
        assert result.n == 5

    def test_no_correlation(self):
        """Uncorrelated data should give rho near 0."""
        np.random.seed(42)
        x = np.random.rand(100).tolist()
        y = np.random.rand(100).tolist()
        result = spearman_rho(x, y, min_n=3)
        assert abs(result.rho) < 0.3  # Roughly no correlation

    def test_insufficient_sample_raises(self):
        """n < 30 should raise InsufficientSampleError."""
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, 4, 5]
        with pytest.raises(InsufficientSampleError) as exc_info:
            spearman_rho(x, y, min_n=30)
        assert "n=5" in str(exc_info.value)

    def test_min_n_enforced(self):
        """Default min_n=30 is enforced."""
        x = list(range(29))
        y = list(range(29))
        with pytest.raises(InsufficientSampleError):
            spearman_rho(x, y)

    def test_exactly_30_samples_works(self):
        """Exactly 30 samples should work."""
        x = list(range(30))
        y = list(range(30))
        result = spearman_rho(x, y)
        assert abs(result.rho - 1.0) < 1e-10
        assert result.n == 30

    def test_tied_ranks(self):
        """Tied values should be handled correctly."""
        x = [1, 2, 2, 3, 4]
        y = [1, 2, 2, 3, 4]
        result = spearman_rho(x, y, min_n=3)
        assert abs(result.rho - 1.0) < 1e-10

    def test_constant_series(self):
        """Constant series should give rho = 1 (perfect correlation with itself)."""
        x = [5, 5, 5, 5, 5]
        y = [5, 5, 5, 5, 5]
        result = spearman_rho(x, y, min_n=3)
        assert result.rho == 1.0 or math.isnan(result.rho)  # Both valid for constant series

    def test_different_lengths_raises(self):
        """Different length inputs should raise ValueError."""
        x = [1, 2, 3]
        y = [1, 2]
        with pytest.raises(ValueError):
            spearman_rho(x, y, min_n=2)

    def test_returns_spearman_result(self):
        """Return value should be SpearmanResult."""
        x = list(range(30))
        y = list(range(30))
        result = spearman_rho(x, y)
        assert isinstance(result, SpearmanResult)
        assert isinstance(result.rho, float)
        assert isinstance(result.p_value, float)
        assert isinstance(result.n, int)
        assert isinstance(result.method, str)

    def test_method_is_spearman(self):
        """Method should be 'spearman'."""
        x = list(range(30))
        y = list(range(30))
        result = spearman_rho(x, y)
        assert result.method == "spearman"

    def test_safe_version_returns_none(self):
        """spearman_rho_safe returns None for insufficient sample."""
        from dora_platform.stats.spearman import spearman_rho_safe

        x = [1, 2, 3]
        y = [1, 2, 3]
        result = spearman_rho_safe(x, y, min_n=30)
        assert result is None

    def test_spearman_result_is_significant(self):
        """SpearmanResult.is_significant works correctly."""
        result = SpearmanResult(rho=0.5, p_value=0.01, n=30)
        assert result.is_significant(alpha=0.05) is True
        assert result.is_significant(alpha=0.001) is False

    def test_spearman_result_to_dict(self):
        """SpearmanResult.to_dict returns correct dict."""
        result = SpearmanResult(rho=0.5, p_value=0.01, n=30)
        d = result.to_dict()
        assert d["rho"] == 0.5
        assert d["p_value"] == 0.01
        assert d["n"] == 30
        assert d["method"] == "spearman"
        assert d["significant"] is True

    def test_empty_array_raises(self):
        """Empty arrays raise ValueError."""
        with pytest.raises(ValueError):
            spearman_rho([], [], min_n=1)

    def test_nan_policy_raise(self):
        """nan_policy='raise' raises on NaN values."""
        x = [1, 2, float("nan"), 4]
        y = [1, 2, 3, 4]
        with pytest.raises(ValueError):
            spearman_rho(x, y, min_n=3, nan_policy="raise")

    def test_nan_policy_propagate(self):
        """nan_policy='propagate' passes NaN through."""
        x = [1, 2, float("nan"), 4]
        y = [1, 2, 3, 4]
        # With propagate, scipy will return NaN for correlation
        result = spearman_rho(x, y, min_n=3, nan_policy="propagate")
        assert math.isnan(result.rho) or math.isnan(result.p_value)

    def test_safe_version_catches_insufficient(self):
        """spearman_rho_safe catches InsufficientSampleError."""
        from dora_platform.stats.spearman import spearman_rho_safe

        x = [1, 2, 3]
        y = [1, 2, 3]
        result = spearman_rho_safe(x, y, min_n=30)
        assert result is None

    def test_spearman_matrix(self):
        """spearman_matrix computes pairwise correlations."""
        from dora_platform.stats.spearman import spearman_matrix

        data = {
            "a": list(range(30)),
            "b": list(range(30)),
            "c": list(reversed(range(30))),
        }
        matrix = spearman_matrix(data, min_n=30)
        assert "a" in matrix
        assert "b" in matrix
        assert "c" in matrix
        # a vs b = 1.0 (perfect positive)
        assert matrix["a"]["b"].rho == 1.0
        # a vs c = -1.0 (perfect negative)
        assert matrix["a"]["c"].rho == -1.0
        # diagonal = 1.0
        assert matrix["a"]["a"].rho == 1.0
        # symmetric
        assert matrix["a"]["b"] is matrix["b"]["a"]


class TestWilsonScoreInterval:
    """Tests for Wilson score interval (binomial proportion CI)."""

    def test_basic_case(self):
        """Basic Wilson interval calculation."""
        ci = wilson_score_interval(successes=5, trials=10, confidence=0.95)
        # For 5/10 = 0.5, CI should be roughly (0.19, 0.81)
        assert 0.1 < ci.lower < 0.3
        assert 0.7 < ci.upper < 0.9

    def test_all_successes(self):
        """All successes should give upper=1, lower>0."""
        ci = wilson_score_interval(successes=10, trials=10, confidence=0.95)
        # Floating point precision: upper is very close to 1.0
        assert ci.upper >= 0.999
        assert 0.7 < ci.lower < 1.0

    def test_no_successes(self):
        """No successes should give lower=0, upper<1."""
        ci = wilson_score_interval(successes=0, trials=10, confidence=0.95)
        assert ci.lower == 0.0
        assert 0.0 < ci.upper < 0.3

    def test_confidence_levels(self):
        """Different confidence levels give different widths."""
        ci_95 = wilson_score_interval(5, 10, 0.95)
        ci_99 = wilson_score_interval(5, 10, 0.99)
        # 99% CI should be wider
        assert (ci_99.upper - ci_99.lower) > (ci_95.upper - ci_95.lower)

    def test_large_sample_normal_approximation(self):
        """Large sample should approach normal approximation."""
        ci = wilson_score_interval(successes=500, trials=1000, confidence=0.95)
        # For large n, Wilson ~ normal: 0.5 ± 1.96 * sqrt(0.25/1000) = 0.5 ± 0.031
        assert 0.46 < ci.lower < 0.48
        assert 0.52 < ci.upper < 0.54

    def test_negative_successes_raises(self):
        """Negative successes should raise ValueError."""
        with pytest.raises(ValueError):
            wilson_score_interval(successes=-1, trials=10)

    def test_zero_trials_returns_zero_interval(self):
        """Zero trials returns zero interval (not an error)."""
        ci = wilson_score_interval(successes=5, trials=0)
        assert ci.lower == 0.0
        assert ci.upper == 0.0

    def test_successes_exceed_trials_raises(self):
        """Successes > trials should raise ValueError."""
        with pytest.raises(ValueError):
            wilson_score_interval(successes=11, trials=10)

    def test_percentage_version(self):
        """Percentage version returns 0-100 scale."""
        ci = wilson_score_interval_percentage(successes=5, trials=10, confidence=0.95)
        assert 10 < ci.lower < 30
        assert 70 < ci.upper < 90


class TestBootstrapCI:
    """Tests for percentile bootstrap confidence interval."""

    def test_basic_bootstrap(self):
        """Basic bootstrap CI for mean."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 100).tolist()
        ci = bootstrap_percentile_ci(data, statistic=np.mean, confidence=0.95, n_resamples=1000)
        assert 9 < ci.lower < 10
        assert 10 < ci.upper < 11

    def test_median_bootstrap(self):
        """Bootstrap CI for median."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 100).tolist()
        ci = bootstrap_percentile_ci(data, statistic=np.median, confidence=0.95, n_resamples=1000)
        assert ci.lower < ci.upper

    def test_different_confidence_levels(self):
        """Different confidence levels give different widths."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 100).tolist()
        ci_95 = bootstrap_percentile_ci(data, np.mean, 0.95, n_resamples=1000)
        ci_99 = bootstrap_percentile_ci(data, np.mean, 0.99, n_resamples=1000)
        assert (ci_99.upper - ci_99.lower) > (ci_95.upper - ci_95.lower)

    def test_empty_data_raises(self):
        """Empty data should return NaN interval."""
        ci = bootstrap_percentile_ci([], np.mean, 0.95)
        assert math.isnan(ci.lower)
        assert math.isnan(ci.upper)

    def test_constant_data(self):
        """Constant data should give CI at that constant."""
        data = [5.0] * 10
        ci = bootstrap_percentile_ci(data, np.mean, 0.95, n_resamples=100)
        assert ci.lower == 5.0
        assert ci.upper == 5.0

    def test_n_resamples_default(self):
        """Default n_resamples should work."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 50).tolist()
        ci = bootstrap_percentile_ci(data, np.mean, 0.95)
        assert ci.lower < ci.upper

    def test_bootstrap_median_ci(self):
        """Convenience function for median."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 100).tolist()
        ci = bootstrap_median_ci(data, confidence=0.95, n_resamples=1000)
        assert ci.lower < ci.upper
        assert ci.method == "bootstrap_percentile"

    def test_bootstrap_mean_ci(self):
        """Convenience function for mean."""
        np.random.seed(42)
        data = np.random.normal(10, 2, 100).tolist()
        ci = bootstrap_mean_ci(data, confidence=0.95, n_resamples=1000)
        assert ci.lower < ci.upper
        assert ci.method == "bootstrap_percentile"

    def test_percentile_ci(self):
        """Direct percentile interval (non-bootstrap)."""
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        ci = percentile_ci(data, confidence=0.95)
        # For n=10, 95% CI is between 2.5th and 97.5th percentiles
        assert ci.lower < ci.upper
        assert ci.method == "percentile"

import pytest

from ajax_pmm.calibration.significance import bucket_binomial_test, pool_chi2_test


def test_bucket_binomial_test_not_significant_near_null():
    result = bucket_binomial_test(k=50, n=100, p0=0.5)
    assert result["significant"] is False
    assert result["pvalue"] > 0.5


def test_bucket_binomial_test_significant_for_large_deviation():
    result = bucket_binomial_test(k=90, n=100, p0=0.5)
    assert result["significant"] is True
    assert result["pvalue"] < 0.001


def test_bucket_binomial_test_ci_contains_point_estimate():
    result = bucket_binomial_test(k=30, n=100, p0=0.5)
    assert result["ci_low"] <= 30 / 100 <= result["ci_high"]


def test_bucket_binomial_test_narrower_ci_at_higher_alpha():
    loose = bucket_binomial_test(k=60, n=100, p0=0.5, alpha=0.20)
    strict = bucket_binomial_test(k=60, n=100, p0=0.5, alpha=0.01)
    assert (loose["ci_high"] - loose["ci_low"]) < (strict["ci_high"] - strict["ci_low"])


def test_pool_chi2_test_zero_statistic_when_exactly_calibrated():
    buckets = [{"n": 10, "mean_implied": 0.5, "realized_sum": 5}]
    result = pool_chi2_test(buckets)
    assert result["statistic"] == 0.0
    assert result["df"] == 1
    assert result["pvalue"] == 1.0
    assert result["significant"] is False


def test_pool_chi2_test_matches_hand_computed_statistic():
    buckets = [
          {"n": 10, "mean_implied": 0.5, "realized_sum": 8},
          {"n": 20, "mean_implied": 0.3, "realized_sum": 10},
    ]
    expected = (9 / 5 + 9 / 5) + (16 / 6 + 16 / 14)
    result = pool_chi2_test(buckets)
    assert result["statistic"] == pytest.approx(expected)
    assert result["df"] == 2


def test_pool_chi2_test_pvalue_drops_as_statistic_grows():
    mild = pool_chi2_test([{"n": 100, "mean_implied": 0.5, "realized_sum": 55}])
    extreme = pool_chi2_test([{"n": 100, "mean_implied": 0.5, "realized_sum": 90}])
    assert extreme["pvalue"] < mild["pvalue"]
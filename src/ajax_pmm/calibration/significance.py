"""Statistical signficance testing for calibration buckets"""

from __future__ import annotations

from scipy.stats import binomtest
from scipy.stats import chi2


def bucket_binomial_test(k: int, n: int, p0: float, alpha: float = 0.05) -> dict:
    result = binomtest(k, n, p0, alternative="two-sided")
    ci = result.proportion_ci(confidence_level=1 - alpha, method="wilson")
    return {
        "pvalue": result.pvalue,
        "ci_low": ci.low,
        "ci_high": ci.high,
        "significant": bool(result.pvalue < alpha),
    }

def pool_chi2_test(buckets: list[dict], alpha: float = 0.05) -> dict:
    statistic = 0.0
    for b in buckets:
        n, p0, k = b["n"], b["mean_implied"], b["realized_sum"]
        expected_yes = n * p0
        expected_no = n * (1- p0)
        observed_no = n - k
        statistic += (k - expected_yes) ** 2 / expected_yes
        statistic += (observed_no - expected_no) ** 2 / expected_no

    df = len(buckets)
    pvalue = chi2.sf(statistic, df)
    return {
        "statistic": statistic,
        "df": df,
        "pvalue": pvalue,
        "significant": bool(pvalue < alpha),
    }
"""Cash-or-nothing binary pricing under a lognormal terminal distribution."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

@dataclass(frozen=True)
class Quote:
    fair: float
    delta: float
    vega: float


def price(spot: float, strike: float, sigma: float, tau: float) -> Quote:
    """P(S_tau > strike) plus sensitivities. sigma and tau must share a time unit"""
    if not (spot > 0 and strike > 0):
        raise ValueError(f"spot and strike must be positive, got {spot=}, {strike=}")
    if not (sigma > 0 and tau > 0):
        raise ValueError(f"sigma and tau must be positive, got {sigma=}, {tau=}")
    v = sigma * math.sqrt(tau)
    d2 = math.log(spot / strike) / v - 0.5 * v
    pdf = _norm_pdf(d2)
    return Quote(fair=_norm_cdf(d2), delta=pdf / (spot * v), vega=-pdf * (d2 + v) / sigma)

def implied_sigma(fair: float, spot: float, strike: float, tau: float,
                  lo: float = 1e-6, hi: float = 5.0, tol: float = 1e-10) -> float | None:
    """Invert price() for sigma, restricted to the monotonic branch"""
    m = math.log(spot / strike)
    if m < 0:
        hi = min(hi, math.sqrt(-2 * m / tau))
    f_lo, f_hi = price(spot, strike, lo, tau).fair, price(spot, strike, hi, tau).fair
    if not min(f_lo, f_hi) <= fair <= max(f_lo, f_hi):
        return None
    increasing = f_hi > f_lo
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if (price(spot, strike, mid, tau).fair < fair) == increasing:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
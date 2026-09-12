"""Tests for the lognormal binary pricing kernel."""

import math

import pytest

from src.fair_value.lognormal import implied_sigma, price

S = 63956.0
SIGMA = 0.004043
TAU = 1.0
LADDER = [-800, -400, -100, 0, 100, 400, 800]


def test_atm_matches_expansion():
    expected = 0.5 - 0.3989 * SIGMA * math.sqrt(TAU) / 2
    assert price(S, S, SIGMA, TAU).fair == pytest.approx(expected, abs=1e-6)

def test_monotone_decreasing_in_strike():
    fairs = [price(S, S + k * 100, SIGMA, TAU).fair for k in range(-10, 11)]
    assert all(a > b for a, b in zip(fairs, fairs[1:]))

def test_deep_itm_and_otm_limits():
    assert price(S, S * 0.5, SIGMA, TAU).fair > 1 - 1e-9
    assert price(S, S * 2.0, SIGMA, TAU).fair < 1e-9


@pytest.mark.parametrize("offset", LADDER)
def test_delta_matches_numeric_derivative(offset):
    k, h = S + offset, 1e-4
    numeric = (price(S + h, k, SIGMA, TAU).fair - price(S - h, k, SIGMA, TAU).fair) / (2 * h)
    assert price(S, k, SIGMA, TAU).delta == pytest.approx(numeric, rel=1e-5)


@pytest.mark.parametrize("offset", LADDER)
def test_vega_matches_numeric_derivative(offset):
    k, h = S + offset, 1e-8
    numeric = (price(S, k, SIGMA + h, TAU).fair - price(S, k, SIGMA - h, TAU).fair) / (2 * h)
    assert price(S, k, SIGMA, TAU).vega == pytest.approx(numeric, rel=1e-4)


@pytest.mark.parametrize("offset", LADDER)
def test_implied_sigma_round_trips(offset):
    k = S + offset
    assert implied_sigma(price(S, k, SIGMA, TAU).fair, S, k, TAU) == pytest.approx(SIGMA, rel=1e-6)

def test_otm_price_is_not_monotonic_in_sigma():
    """Guards the hi-clamp: OTM binaries peak in sigma at v* = sqrt(2|ln(S/K|)"""
    k = S + 400
    sigma_star = math.sqrt(-2 * math.log(S / k) / TAU)
    peak = price(S, k, sigma_star, TAU).fair
    assert peak > price(S, k, sigma_star * 0.5, TAU).fair

def test_implied_sigma_returns_none_when_unreachable():
    assert implied_sigma(0.999999, S, S + 400, TAU) is None


@pytest.mark.parametrize("args", [
    (0.0, S, SIGMA, TAU),
    (-S, S, SIGMA, TAU),
    (S, 0.0, SIGMA, TAU),
    (S, S, 0.0, TAU),
    (S, S, -SIGMA, TAU),
    (S, S, SIGMA, 0.0),
])
def test_validation_rejects_nonpositive_inputs(args):
    with pytest.raises(ValueError):
        price(*args)

def test_ladder_implies_nonnegative_density():
    """No-arbitrage: adjacent-strike price differences are the implied PDF, must be >= 0"""
    fairs = [price(S, S + k * 100, SIGMA, TAU).fair for k in range(-10, 11)]
    assert all(a - b >= 0 for a, b in zip(fairs, fairs[1:]))
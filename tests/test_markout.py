"""Tests for the passive-fill markout / adverse-selection module."""

import pytest

from ajax_pmm.analysis.markout import (
    BAR_SECONDS,
    TAKER_BUY,
    TAKER_SELL,
    Bar,
    adverse_selection,
    classify_flow,
    infer_fill,
    infer_fills,
    markout,
    markout_curve
)

T0 = 1787623260


def bar(i=0, bid=0.40, ask=0.42, last=0.0, volume=0.0):
    """A no-trade barby default; pass last and volume to make it trade"""
    return Bar(end_ts=T0 + i * BAR_SECONDS, bid=bid, ask=ask, last=last, volume=volume)

def test_mid_and_half_spread():
    b = bar()
    assert b.mid == pytest.approx(0.41)
    assert b.half_spread == pytest.approx(0.01)


@pytest.mark.parametrize("bid,ask", [(0.0, 0.42), (0.40, 0.0), (0.0, 0.0)])
def test_one_sided_bar_has_no_mid_or_spread(bid, ask):
    b = bar(bid=bid, ask=ask)
    assert not b.two_sided
    with pytest.raises(ValueError):
        _ = b.mid
    with pytest.raises(ValueError):
        _ = b.half_spread


def test_classify_flow_none_without_a_trade():
    assert classify_flow(bar(volume=0.0, last=0.42)) is None
    assert classify_flow(bar(volume=10.0, last=0.0)) is None

def test_classify_flow_none_when_one_sided():
    assert classify_flow(bar(bid=0.0, last=0.42, volume=10.0)) is None


@pytest.mark.parametrize("last", [0.42, 0.45])
def test_classify_flow_at_or_through_the_ask_is_a_taker_buy(last):
      assert classify_flow(bar(last=last, volume=10.0)) == TAKER_BUY


@pytest.mark.parametrize("last", [0.40, 0.35])
def test_classify_flow_at_or_through_the_bid_is_a_taker_sell(last):
      assert classify_flow(bar(last=last, volume=10.0)) == TAKER_SELL

def test_classify_flow_inside_the_spread_falls_back_to_the_mid():
    assert classify_flow(bar(bid=0.25, ask=0.75, last=0.60, volume=10.0)) == TAKER_BUY
    assert classify_flow(bar(bid=0.25, ask=0.75, last=0.40, volume=10.0)) == TAKER_SELL

def test_classify_flow_at_the_mid_is_ambiguous():
      assert classify_flow(bar(bid=0.25, ask=0.75, last=0.5, volume=10.0)) is None

def test_infer_fill_taker_buy_makes_us_short_at_the_ask():
    f = infer_fill([bar(3, last=0.42, volume=10.0)], 0)
    assert f.maker_short
    assert f.price == pytest.approx(0.42)
    assert f.mid_at_fill == pytest.approx(0.41)
    assert f.half_spread == pytest.approx(0.01)
    assert f.index == 0
    assert f.end_ts == T0 + 3 * BAR_SECONDS

def test_infer_fill_taker_sell_makes_us_long_at_the_bid():
    f = infer_fill([bar(last=0.40, volume=10.0)], 0)
    assert not f.maker_short
    assert f.price == pytest.approx(0.40)

def test_infer_fill_none_on_a_bar_that_did_not_trade():
    assert infer_fill([bar()], 0) is None

def test_infer_fills_keeps_source_indices():
    bars = [bar(0), bar(1, last=0.42, volume=10.0), bar(2), bar(3, last=0.40, volume=10.0)]
    fills = infer_fills(bars)
    assert [f.index for f in fills] == [1, 3]
    assert [f.maker_short for f in fills] == [True, False]

def test_markout_positive_when_the_mark_moves_our_way():
    short = infer_fill([bar(last=0.42, volume=10.0)], 0)
    long_ = infer_fill([bar(last=0.40, volume=10.0)], 0)
    assert markout(short, 0.30) == pytest.approx(0.12)
    assert markout(long_, 0.50) == pytest.approx(0.10)

def test_markout_negative_when_the_mark_runs_over_us():
    short = infer_fill([bar(last=0.42, volume=10.0)], 0)
    assert markout(short, 0.50) == pytest.approx(-0.08)

def test_no_adverse_selection_when_the_mid_does_not_move():
    """A fill that keeps the full half-spread is by definition not picked off."""
    f = infer_fill([bar(last=0.42, volume=10.0)], 0)
    assert adverse_selection(f, f.mid_at_fill) == pytest.approx(0.0)


@pytest.mark.parametrize("future_mid", [0.10, 0.41, 0.90])
def test_markout_and_adverse_selection_sum_to_the_half_spread(future_mid):
    f = infer_fill([bar(last=0.42, volume=10.0)], 0)
    assert markout(f, future_mid) + adverse_selection(f, future_mid) == pytest.approx(f.half_spread)

def test_markout_curve_marks_each_horizon():
    bars = [
        bar(0),
        bar(1, last=0.42, volume=10.0),
        bar(2, bid=0.44, ask=0.46),
        bar(3, bid=0.30, ask=0.32),
    ]
    curve = markout_curve(bars, infer_fill(bars, 1), [1, 2])
    assert curve[1] == pytest.approx(-0.03)
    assert curve[2] == pytest.approx(0.11)

def test_markout_curve_zero_horizon_returns_the_half_spread():
    bars = [bar(0, last=0.42, volume=10.0)]
    assert markout_curve(bars, infer_fill(bars, 0), [0])[0] == pytest.approx(0.01)


def test_markout_curve_none_past_the_end():
    bars = [bar(0, last=0.42, volume=10.0), bar(1)]
    assert markout_curve(bars, infer_fill(bars, 0), [5]) == {5: None}


def test_markout_curve_none_before_the_start():
    """Guards the lower bound: a negative index would silently wrap to the end of the list."""
    bars = [bar(0, last=0.42, volume=10.0), bar(1)]
    assert markout_curve(bars, infer_fill(bars, 0), [-1]) == {-1: None}


def test_markout_curve_none_across_a_missing_minute():
    """A gap in the candles means bars[j] is not the bar k minutes later."""
    bars = [bar(0, last=0.42, volume=10.0), bar(5)]
    assert markout_curve(bars, infer_fill(bars, 0), [1]) == {1: None}


def test_markout_curve_none_when_the_reference_bar_is_one_sided():
    bars = [bar(0, last=0.42, volume=10.0), bar(1, ask=0.0)]
    assert markout_curve(bars, infer_fill(bars, 0), [1]) == {1: None}
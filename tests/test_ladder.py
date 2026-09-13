import pytest

from ajax_pmm.calibration.events import Strike
from ajax_pmm.kalshi.ladder import select_near_money


def mk(*ks):
    return [Strike(ticker=f"T{k}", floor_strike=float(k), result="no") for k in ks]

def test_picks_nearest_and_sorts_ascending():
    got = select_near_money(mk(100, 200, 300, 400, 500), 320.0, 3)
    assert [s.floor_strike for s in got] == [200.0, 300.0, 400.0]

def test_handles_n_larger_than_ladder():
    assert len(select_near_money(mk(100, 200), 150.0, 10)) == 2

def test_tie_breaks_on_lower_strike():
    assert select_near_money(mk(100, 200), 150.0, 1)[0].floor_strike == 100.0

def test_spot_outside_ladder_takes_the_edge():
    got = select_near_money(mk(100, 200, 300), 9999.0, 2)
    assert [s.floor_strike for s in got] == [200.0, 300.0]

def test_rejects_nonpositive_n():
    with pytest.raises(ValueError):
        select_near_money(mk(100), 100.0, 0)
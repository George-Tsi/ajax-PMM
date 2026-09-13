from ajax_pmm.coinbase.price_lookup import price_at


TIMESTAMPS = [100, 200, 300]
CLOSES = [10.0, 20.0, 30.0]


def test_price_at_before_first_timestamp():
    assert price_at(TIMESTAMPS, CLOSES, 50) == 10.0


def test_price_at_after_last_timestamp():
    assert price_at(TIMESTAMPS, CLOSES, 999) == 30.0


def test_price_at_exact_match():
    assert price_at(TIMESTAMPS, CLOSES, 200) == 20.0


def test_price_at_closer_to_earlier_candle():
    assert price_at(TIMESTAMPS, CLOSES, 140) == 10.0  # 40 away from 100, 60 away from 200


def test_price_at_closer_to_later_candle():
    assert price_at(TIMESTAMPS, CLOSES, 260) == 30.0  # 40 away from 300, 60 away from 200


def test_price_at_tie_prefers_earlier_candle():
    assert price_at(TIMESTAMPS, CLOSES, 150) == 10.0  # exactly halfway between 100 and 200

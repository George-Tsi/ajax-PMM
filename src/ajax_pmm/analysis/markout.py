"""Markout analysis: what a passive fill was worth some minutes after it happened"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

BAR_SECONDS = 60

TAKER_BUY = 1 #taker lifted the ask -> the resting maker sold
TAKER_SELL = -1 # taker hit the bid -> the resting maker bought


@dataclass(frozen=True)
class Bar:
    """One minute of one strike.
    
    bid/ask are bar-close quotes, but last is the last trade price at any point in the bar and 
    Kalshi carries it forward across no-trade bars, so volume is the only reliable trade flag.
    volume is dollar notional, not contracts."""

    end_ts: int
    bid: float
    ask: float
    last: float
    volume: float

    @property
    def two_sided(self) -> bool:
        return self.bid > 0 and self.ask > 0

    @property
    def mid(self) -> float:
        if not self.two_sided:
            raise ValueError(f"mid undefined without both quotes, got {self.bid=}, {self.ask=}")
        return 0.5 * (self.bid +self.ask)

    @property
    def half_spread(self) -> float:
        if not self.two_sided:
            raise ValueError(f"spread undefined without both quotes, got {self.bid=}, {self.ask=}")
        return 0.5 * (self.ask - self.bid)

def classify_flow(bar: Bar) -> int | None:
    """Quote-rule trade signing. None when the bar did not trade or the side is ambiguous"""
    if bar.volume <= 0 or bar.last <= 0 or not bar.two_sided:
         return None
    if bar.last >= bar.ask:
        return TAKER_BUY
    if bar.last <= bar.bid:
        return TAKER_SELL
    mid = bar.mid
    if bar.last == mid:
        return None
    return TAKER_BUY if bar.last > mid else TAKER_SELL

@dataclass(frozen=True)
class Fill: 
    """A hypothetical passive fill: we were resting at the touch and the taker came to us"""

    index: int
    end_ts: int
    maker_short: bool # True: we sold at the ask. False: we bought at the bid
    price: float
    mid_at_fill: float
    half_spread: float

def infer_fill(bars: Sequence[Bar], i: int) -> Fill | None:
    bar = bars[i]
    side = classify_flow(bar)
    if side is None:
        return None
    maker_short = side == TAKER_BUY
    return Fill(
        index=i,
        end_ts=bar.end_ts,
        maker_short=maker_short,
        price=bar.ask if maker_short else bar.bid,
        mid_at_fill=bar.mid,
        half_spread=bar.half_spread,
    )

def infer_fills(bars: Sequence[Bar]) -> list[Fill]:
    return [f for f in (infer_fill(bars, i) for i in range(len(bars))) if f is not None]

def markout(fill: Fill, future_mid: float) -> float:
    """Maker P&L per contract at a later mark. Positive is good for the maker."""
    return fill.price - future_mid if fill.maker_short else future_mid - fill.price

def adverse_selection(fill: Fill, future_mid: float) -> float: 
    """The half-spread the maker failed to keep. Positive means the mark moved against them."""
    return fill.half_spread - markout(fill, future_mid)

def markout_curve(
        bars: Sequence[Bar], fill: Fill, horizons: Sequence[int]
) -> dict[int, float | None]:
    """Markout at each horizon in minutes. None where the reference bar is missing or one-sided"""
    curve: dict[int, float | None] = {}
    for k in horizons:
        j = fill.index + k
        if not 0 <= j < len(bars):
            curve[k] = None
            continue
        bar = bars[j]
        stale = bar.end_ts !=fill.end_ts + k * BAR_SECONDS
        curve[k] = None if stale or not bar.two_sided else markout(fill, bar.mid)
    return curve
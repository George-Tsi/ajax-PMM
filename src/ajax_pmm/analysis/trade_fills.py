"""Turn real exchange trades into maker fills, replacing the quote-rule guess.

`ajax_pmm.analysis.markout.infer_fills` reconstructs a hypothetical fill from candle data, which
is biased: it signs trades against bar-close quotes and so picks bars where the print landed on
the lucky side of where the quote settled (2026-09-13). Kalshi publishes `taker_side` directly,
so the side and the price are both exact here and only the future mid comes from candles.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Sequence
from itertools import groupby
from pathlib import Path

from ajax_pmm.analysis.markout import BAR_SECONDS, Bar, Fill

REQUIRED = {"ticker", "created_ts", "yes_price", "taker_side", "is_block_trade", "count"}


def bar_index(bars: Sequence[Bar], trade_ts: float) -> int | None:
    """Index of the minute bar a trade falls inside, or None if no bar covers it.

    Bars are stamped at their close, so a trade at t belongs to the bar whose end_ts is the next
    minute boundary at or after t.
    """
    if not bars:
        return None
    target = -(-int(trade_ts) // BAR_SECONDS) * BAR_SECONDS
    lo, hi = 0, len(bars) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid].end_ts == target:
            return mid
        if bars[mid].end_ts < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def iter_ticker_trades(path: str | Path) -> Iterator[tuple[str, list[dict]]]:
    """Yield (ticker, rows) groups. Relies on the puller writing one ticker at a time."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        for ticker, rows in groupby(reader, key=lambda r: r["ticker"]):
            yield ticker, list(rows)


def fills_from_trades(bars: Sequence[Bar], rows: Sequence[dict]) -> list[Fill]:
    """Maker fills implied by real trades on one strike.

    A taker buying YES is filled by a maker who sold YES, so the maker is short. Block trades are
    negotiated off-book and are not fills a resting quote could have taken, so they are dropped.
    `mid_at_fill` and `half_spread` come from the bar-close quote and are context only -- markout
    itself needs just the trade price and the side, both exact.
    """
    out: list[Fill] = []
    for r in rows:
        if r["is_block_trade"] == "1":
            continue
        i = bar_index(bars, float(r["created_ts"]))
        if i is None or not bars[i].priced:
            continue
        out.append(Fill(
            index=i,
            end_ts=bars[i].end_ts,
            maker_short=r["taker_side"] == "yes",
            price=float(r["yes_price"]),
            mid_at_fill=bars[i].mid,
            half_spread=bars[i].half_spread,
        ))
    return out


def fills_with_size(bars: Sequence[Bar], rows: Sequence[dict]) -> list[tuple[Fill, float]]:
    """Maker fills paired with contract count.

    Kept separate from fills_from_trades because rows are dropped during placement, so pairing
    fills back to sizes by position afterwards would silently misalign.
    """
    out: list[tuple[Fill, float]] = []
    for r in rows:
        if r["is_block_trade"] == "1":
            continue
        i = bar_index(bars, float(r["created_ts"]))
        if i is None or not bars[i].priced:
            continue
        out.append((Fill(
            index=i,
            end_ts=bars[i].end_ts,
            maker_short=r["taker_side"] == "yes",
            price=float(r["yes_price"]),
            mid_at_fill=bars[i].mid,
            half_spread=bars[i].half_spread,
        ), float(r["count"])))
    return out

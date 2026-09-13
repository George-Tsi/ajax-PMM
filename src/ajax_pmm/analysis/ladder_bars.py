"""Load the KXBTCD ladder candle CSV into per-strike bar sequences."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ajax_pmm.analysis.markout import Bar

REQUIRED = {"event_ticker", "ticker", "floor_strike", "close_ts",
            "end_ts", "yes_bid_close", "yes_ask_close", "last_price", "volume"}


@dataclass(frozen=True)
class StrikeSeries:
    """One strike's minute bars, ascending in time"""

    ticker: str
    event_ticker: str
    floor_strike: float
    close_ts: int
    bars: list[Bar]


def load_ladder_candles(path: str | Path) -> list[StrikeSeries]:
    bars: dict[str, list[Bar]] = defaultdict(list)
    meta: dict[str, tuple[str, float, int]] = {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        for r in reader:
            ticker = r["ticker"]
            if ticker not in meta:
                meta[ticker] = (r["event_ticker"], float(r["floor_strike"]), int(r["close_ts"]))
            bars[ticker].append(Bar(
                end_ts=int(r["end_ts"]),
                bid=float(r["yes_bid_close"]),
                ask=float(r["yes_ask_close"]),
                last=float(r["last_price"]),
                volume=float(r["volume"]),
            ))
    series = []
    for ticker, rows in bars.items():
        event_ticker, floor_strike, close_ts = meta[ticker]
        rows.sort(key=lambda b: b.end_ts)
        series.append(StrikeSeries(ticker, event_ticker, floor_strike, close_ts, rows))
    series.sort(key=lambda s: (s.event_ticker, s.floor_strike))
    return series
"""Load settled Kalshi event ladders from the settled-markets CSV."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Strike:
    ticker: str
    floor_strike: float
    result: str


@dataclass(frozen=True)
class EventLadder:
    event_ticker: str
    open_ts: int
    close_ts: int
    strikes: list[Strike]


def _parse_ts(raw: str) -> int:
    return int(datetime.fromisoformat(raw).timestamp())


def load_events(path: Path) -> list[EventLadder]:
    by_event: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_event[row["event_ticker"]].append(row)

    events = []
    for event_ticker, rows in by_event.items():
        open_ts = _parse_ts(rows[0]["open_time"])
        close_ts = _parse_ts(rows[0]["close_time"])
        if close_ts - open_ts != 3600:
            continue  # not the standard hourly ladder
        strikes = [
            Strike(ticker=r["ticker"], floor_strike=float(r["floor_strike"]), result=r["result"])
            for r in rows
            if r["floor_strike"] and r["result"]
        ]
        if not strikes:
            continue
        events.append(EventLadder(
            event_ticker=event_ticker,
            open_ts=open_ts,
            close_ts=close_ts,
            strikes=strikes,
        ))
    return events

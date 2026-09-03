"""Calibration check on KXBTCD: is Kalshi's implied probability accurate at T-60min (mkt open), using only the near-the-money strike, 
selected via external BTC price feed (coinbase) rather than the realized outcome"""

from __future__ import annotations

import csv
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

from src.coinbase.client import CoinbaseClient, Candle
from src.kalshi.client import KalshiClient, KalshiAPIError

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SETTLED_CSV = DATA_DIR / "kxbtcd_settled_20260825_0346.csv"
BTC_PRICE_CACHE_CSV = DATA_DIR / "btcusd_1min_20260618_20260825.csv"

BTC_PRODUCT_ID = "BTC-USD"
KALSHI_SERIES_TICKER = "KXBTCD"
QUOTE_SEARCH_WINDOW_S = 300 # scan up to 5 min after T for the first valid bid/ask
IN_BUCKETS = 10

# Once each the settled CSV is grouped by event_ticker, each hourly ladder needs to carry its own list of strikes

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
        

# fetching and Caching BTC price history

def _save_candles(path: Path, candles: list[Candle]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "low", "high", "open", "close", "volume"])
        for c in candles:
            writer.writerow([c.ts, c.low, c.high, c.open, c.close, c.volume])


def _load_cached_candles(path: Path) -> list[Candle]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(Candle(
                ts=int(row["ts"]),
                low=float(row["low"]),
                high=float(row["high"]),
                open=float(row["open"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
        ))
    return out


def fetch_btc_price_history(client: CoinbaseClient, start_ts: int, end_ts: int) -> list[Candle]:
    if BTC_PRICE_CACHE_CSV.exists():
        return _load_cached_candles(BTC_PRICE_CACHE_CSV)
    candles = client.get_candles(BTC_PRODUCT_ID, start_ts, end_ts)
    _save_candles(BTC_PRICE_CACHE_CSV, candles)
    return candles

def build_price_lookup(candles: list[Candle]) -> tuple[list[int], list[float]]:
    ordered = sorted(candles, key=lambda c: c.ts)
    timestamps = [c.ts for c in ordered]
    closes = [c.close for c in ordered]
    return timestamps, closes


def price_at(timestamps: list[int], closes: list[float], ts: int) -> float:
    i = bisect_left(timestamps, ts)
    if i == 0:
        return closes[0]
    if i == len(timestamps):
        return closes[-1]
    before, after = timestamps[i -1], timestamps[i]
    return closes[i - 1] if (ts - before) <= (after - ts) else closes[i]

# Match event to its ATM strike and Kalshi's implied probability at T

def implied_prob_at_t(kalshi: KalshiClient, event: EventLadder, spot: float) -> tuple[float, str] | None:
    strike = min(event.strikes, key=lambda s: abs(s.floor_strike - spot))
    try:
        candles = kalshi.get_candlesticks(
            series_ticker=KALSHI_SERIES_TICKER,
            ticker=strike.ticker,
            start_ts=event.open_ts,
            end_ts=event.open_ts + QUOTE_SEARCH_WINDOW_S,
            period_interval=1,
        )
    except KalshiAPIError:
        return None
    for c in candles:
        if c.yes_bid_close > 0 and c.yes_ask_close > 0:
            return (c.yes_bid_close + c.yes_ask_close) / 2, strike.result
    return None


# To loop over all 1528 events

def bucket_index(price: float, n_buckets: int) -> int:
    return min(int(price * n_buckets), n_buckets - 1)

def calibration_table(pairs: list[tuple[float, str]], n_buckets: int) -> list[dict]:
    sums = defaultdict(lambda: {"n": 0, "implied_sum": 0.0, "realized_sum": 0})
    for implied, result in pairs:
        b = bucket_index(implied, n_buckets)
        realized = 1 if result == "yes" else 0
        sums[b]["n"] += 1
        sums[b]["implied_sum"] += implied
        sums[b]["realized_sum"] += realized

    table = []
    for b in range(n_buckets):
        s = sums[b]
        if s["n"] == 0:
            continue
        table.append({
            "bucket": b,
            "n": s["n"],
            "mean_implied": s["implied_sum"] / s["n"],
            "realized_rate": s["realized_sum"] / s["n"],
        })
    return table


PAIRS_CACHE_CSV = DATA_DIR / "atm_calibration_pairs.csv"


def _save_pairs(path: Path, pairs: list[tuple[float, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["implied", "result"])
        writer.writerows(pairs)


def _load_cached_pairs(path: Path) -> list[tuple[float, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [(float(row["implied"]), row["result"]) for row in csv.DictReader(f)]


def main() -> None:
    events = load_events(SETTLED_CSV)

    if PAIRS_CACHE_CSV.exists():
        pairs = _load_cached_pairs(PAIRS_CACHE_CSV)
        misses = len(events) - len(pairs)
    else:
        start_ts = min(e.open_ts for e in events)
        end_ts = max(e.close_ts for e in events)
        candles = fetch_btc_price_history(CoinbaseClient(), start_ts, end_ts)
        timestamps, closes = build_price_lookup(candles)

        kalshi = KalshiClient()
        pairs = []
        misses = 0
        for event in events:
            spot = price_at(timestamps, closes, event.open_ts)
            result = implied_prob_at_t(kalshi, event, spot)
            if result is None:
                misses += 1
                continue
            pairs.append(result)
            if len(pairs) % 100 == 0:
                print(f"...{len(pairs)}/{len(events)} processed")
        _save_pairs(PAIRS_CACHE_CSV, pairs)

    print(f"{len(pairs)} events with avalid quote, {misses} skipped (no quote in window)")

    table = calibration_table(pairs, IN_BUCKETS)
    for row in table:
        gap = row["realized_rate"] - row["mean_implied"]
        print(f"bucket {row['bucket']}: n={row['n']:>4} implied={row['mean_implied']:.3f} "
                f"realized={row['realized_rate']:.3f} gap={gap:+.3f}")


if __name__ == "__main__":
    main()
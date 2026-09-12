"""Pull 1-min candlestick history for the near-the-money strikes of each settled hourly ladder"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from src.calibration.events import load_events
from src.coinbase.price_lookup import build_price_lookup, load_cached_candles, price_at
from src.kalshi.client import KalshiAPIError, KalshiClient
from src.kalshi.ladder import select_near_money

SERIES = "KXBTCD"
N_STRIKES = 16
RETENTION_DAYS = 67
SETTLED_CSV = Path("data/kxbtcd_settled_20260825_0346.csv")
BTC_CSV = Path("data/btcusd_1min_20260618_20260825.csv")
OUT_CSV = Path("data/kxbtcd_ladder_candles.csv")
FIELDS = [
      "event_ticker", "ticker", "floor_strike", "open_ts", "close_ts", "spot_at_open",
      "end_ts", "yes_bid_close", "yes_ask_close", "last_price", "volume",
]

def completed_events(path: Path) -> set[str]:
      if not path.exists():
          return set()
      with path.open(newline="", encoding="utf-8") as f:
          return {row["event_ticker"] for row in csv.DictReader(f)}


def main() -> None:
    events = load_events(SETTLED_CSV)
    timestamps, closes = build_price_lookup(load_cached_candles(BTC_CSV))
    done = completed_events(OUT_CSV)
    cutoff = int(time.time()) - RETENTION_DAYS * 86400
    todo = [e for e in events if e.close_ts > cutoff and e.event_ticker not in done]
    aged = sum(1 for e in events if e.close_ts <= cutoff)
    print(f"{len(events)} events: {aged} aged out, {len(done)} already pulled, {len(todo)} to go")

    client = KalshiClient()
    write_header = not OUT_CSV.exists() or OUT_CSV.stat().st_size == 0
    total_rows = total_misses = 0
    with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        for i, event in enumerate(todo, 1):
            spot = price_at(timestamps, closes, event.open_ts)
            rows, misses = [], 0
            for strike in select_near_money(event.strikes, spot, N_STRIKES):
                try:
                    bars = client.get_candlesticks(
                        SERIES, strike.ticker, event.open_ts, event.close_ts
                    )
                except KalshiAPIError:
                    misses += 1
                    continue
                rows.extend({
                    "event_ticker": event.event_ticker,
                    "ticker": strike.ticker,
                    "floor_strike": strike.floor_strike,
                    "open_ts": event.open_ts,
                    "close_ts": event.close_ts,
                    "spot_at_open": spot,
                    "end_ts": b.end_ts,
                    "yes_bid_close": b.yes_bid_close,
                    "yes_ask_close": b.yes_ask_close,
                    "last_price": b.last_price,
                    "volume": b.volume,
                } for b in bars)
            writer.writerows(rows)
            f.flush()
            total_rows += len(rows)
            total_misses += misses
            print(f"[{i}/{len(todo)}] {event.event_ticker} rows={len(rows)} misses={misses}", flush=True)

    print(f"\ndone: {total_rows:,} rows, {total_misses} strike misses -> {OUT_CSV}")


if __name__ == "__main__":
    main()

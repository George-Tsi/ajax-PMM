"""Calibration check on KXBTCD: is Kalshi's implied probability accurate at T-60min (mkt open), using only the near-the-money strike, 
selected via external BTC price feed (coinbase) rather than the realized outcome"""

from __future__ import annotations

import csv
from pathlib import Path

from ajax_pmm.calibration.events import EventLadder, load_events
from ajax_pmm.calibration.stats import calibration_table
from ajax_pmm.coinbase.client import CoinbaseClient
from ajax_pmm.coinbase.price_lookup import build_price_lookup, fetch_price_history, price_at
from ajax_pmm.kalshi.client import KalshiClient, KalshiAPIError

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SETTLED_CSV = DATA_DIR / "kxbtcd_settled_20260825_0346.csv"
BTC_PRICE_CACHE_CSV = DATA_DIR / "btcusd_1min_20260618_20260825.csv"
PAIRS_CACHE_CSV = DATA_DIR / "atm_calibration_pairs.csv"

BTC_PRODUCT_ID = "BTC-USD"
KALSHI_SERIES_TICKER = "KXBTCD"
QUOTE_SEARCH_WINDOW_S = 300 # scan up to 5 min after T for the first valid bid/ask
IN_BUCKETS = 10

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
        candles = fetch_price_history(CoinbaseClient(), BTC_PRICE_CACHE_CSV, BTC_PRODUCT_ID, start_ts, end_ts)
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
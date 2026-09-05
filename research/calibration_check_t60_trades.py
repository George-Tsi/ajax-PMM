"""Robustness check: does calibration change if implied probability is derived from 
the last trade in the T-60 window instead of the quote midpoint?"""

from __future__ import annotations

import csv

from research.calibration_check_t60 import implied_prob_at_t

from pathlib import Path

from src.calibration.events import EventLadder, load_events
from src.calibration.stats import calibration_table, print_calibration_table
from src.calibration.significance import bucket_binomial_test, pool_chi2_test
from src.coinbase.client import CoinbaseClient
from src.coinbase.price_lookup import build_price_lookup, fetch_price_history, price_at
from src.kalshi.client import KalshiClient, KalshiAPIError

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SETTLED_CSV = DATA_DIR / "kxbtcd_settled_20260825_0346.csv"
BTC_PRICE_CACHE_CSV = DATA_DIR / "btcusd_1min_20260618_20260825.csv"
PAIRS_CACHE_CSV = DATA_DIR / "atm_calibration_quote_vs_trade_pairs.csv"

BTC_PRODUCT_ID = "BTC-USD"
KALSHI_SERIES_TICKER = "KXBTCD"
QUOTE_SEARCH_WINDOW_S = 300 # scan up to 5 min after T for a trade, same window as quote-midpoint check
IN_BUCKETS = 10
TAIL_BUCKETS = {1, 2, 3, 7, 8} # excludes 0 and 9 (near-certain) and 4/5/6 (well-calibrated core)
ALPHA = 0.05


def implied_prob_from_trade(kalshi: KalshiClient, event: EventLadder, spot: float) -> tuple[float, str] | None:
    strike = min(event.strikes, key=lambda s: abs(s.floor_strike - spot))
    trades = kalshi.iter_trades(
        ticker=strike.ticker,
        min_ts=event.open_ts,
        max_ts=event.open_ts + QUOTE_SEARCH_WINDOW_S,
    )
    try:
        trade = next(trades, None)
    except KalshiAPIError:
        return None
    if trade is None:
        return None
    return trade.yes_price, strike.result


def _save_pairs(path: Path, rows: list[tuple[float, float, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["implied_quote", "implied_trade", "result"])
        writer.writerows(rows)


def _load_cached_pairs(path: Path) -> list[tuple[float, float, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            (float(row["implied_quote"]), float(row["implied_trade"]), row["result"])
              for row in csv.DictReader(f)
        ] 

def main() -> None:
    events = load_events(SETTLED_CSV)

    if PAIRS_CACHE_CSV.exists():
        rows = _load_cached_pairs(PAIRS_CACHE_CSV)
    else:
        start_ts = min(e.open_ts for e in events)
        end_ts = max(e.close_ts for e in events)
        candles = fetch_price_history(CoinbaseClient(), BTC_PRICE_CACHE_CSV, BTC_PRODUCT_ID, start_ts, end_ts)
        timestamps, closes = build_price_lookup(candles)

        kalshi = KalshiClient()
        rows = []
        for i, event in enumerate(events, start=1):
            spot = price_at(timestamps, closes, event.open_ts)
            quote_result = implied_prob_at_t(kalshi, event, spot)
            trade_result = implied_prob_from_trade(kalshi, event, spot)
            if quote_result is not None and trade_result is not None:
                implied_quote, result = quote_result
                implied_trade, _ = trade_result
                rows.append((implied_quote, implied_trade, result))
            if i % 100 == 0:
                print(f"...{i}/{len(events)} processed")
        _save_pairs(PAIRS_CACHE_CSV, rows)

    print(f"{len(rows)} events with both a valid quote and a valid trade in window")

    print_calibration_table([(q, r) for q, t, r in rows], IN_BUCKETS, label="quote-midpoint calibration")
    print_calibration_table([(t, r) for q, t, r in rows], IN_BUCKETS, label="last-trade calibration")

    trade_pairs = [(t, r) for q, t, r in rows]
    table = calibration_table(trade_pairs, IN_BUCKETS)
    tail_rows = [row for row in table if row["bucket"] in TAIL_BUCKETS]

    bonferroni_alpha =ALPHA / len(tail_rows)
    print("\n--- last-trade tail buket significance (binomial test per buckt) ---")
    for row in tail_rows:
        test = bucket_binomial_test(row["realized_sum"], row["n"], row["mean_implied"], alpha=bonferroni_alpha)
        print(f"bucket {row['bucket']}: n={row['n']:>4} implied={row['mean_implied']:.3f} "
              f"realized={row['realized_rate']:.3f} pvalue={test['pvalue']:.4f} "
              f"ci=({test['ci_low']:.3f}, {test['ci_high']:.3f}) significant={test['significant']}")
       
    pooled = pool_chi2_test(tail_rows, alpha=ALPHA)
    print(f"\npooled chi2 test on tail buckets: statistic={pooled['statistic']:.3f} "
        f"df={pooled['df']} pvalue={pooled['pvalue']:.4f} significant={pooled['significant']}")


if __name__ == "__main__":
    main()

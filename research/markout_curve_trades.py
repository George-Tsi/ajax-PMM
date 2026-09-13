"""Markout curve from real exchange trades, clustered by event.

Same measurement as markout_curve.py, but fills come from Kalshi's published taker_side instead
of the quote-rule guess. Also reports markout net of the sample's own mid drift: a mid that
drifts up costs a short maker and pays a long one, which is a property of the period rather than
of market making, so it is removed per fill rather than from the blend.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from ajax_pmm.analysis.ladder_bars import load_ladder_candles
from ajax_pmm.analysis.markout import BAR_SECONDS, markout_curve
from ajax_pmm.analysis.markout_stats import horizon_stats
from ajax_pmm.analysis.trade_fills import fills_from_trades, iter_ticker_trades

LADDER_PATH = "data/kxbtcd_ladder_candles.csv"
TRADES_PATH = "data/kxbtcd_trades.csv"
DEFAULT_HORIZONS = [1, 5, 15, 30]


def mid_drift(series, horizons: list[int]) -> dict[int, float]:
    """Mean mid change over k minutes across every bar pair, as a per-horizon baseline."""
    total: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for s in series:
        bars = s.bars
        for i, b in enumerate(bars):
            if not b.two_sided:
                continue
            for k in horizons:
                j = i + k
                if j >= len(bars):
                    continue
                nxt = bars[j]
                if nxt.end_ts != b.end_ts + k * BAR_SECONDS or not nxt.two_sided:
                    continue
                total[k] += nxt.mid - b.mid
                count[k] += 1
    return {k: (total[k] / count[k] if count[k] else 0.0) for k in horizons}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", default=LADDER_PATH)
    ap.add_argument("--trades", default=TRADES_PATH)
    ap.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    args = ap.parse_args()

    series = load_ladder_candles(args.ladder)
    by_ticker = {s.ticker: s for s in series}
    print(f"{len(series):,} strikes loaded", flush=True)

    drift = mid_drift(series, args.horizons)
    print("mid drift baseline: " + "  ".join(
        f"{k}m {100 * v:+.4f}c" for k, v in sorted(drift.items())), flush=True)

    raw = {k: defaultdict(list) for k in args.horizons}
    net = {k: defaultdict(list) for k in args.horizons}
    short = {k: defaultdict(list) for k in args.horizons}
    long_ = {k: defaultdict(list) for k in args.horizons}
    n_fills = n_skipped = 0

    for ticker, rows in iter_ticker_trades(args.trades):
        s = by_ticker.get(ticker)
        if s is None:
            n_skipped += len(rows)
            continue
        for fill in fills_from_trades(s.bars, rows):
            n_fills += 1
            for k, value in markout_curve(s.bars, fill, args.horizons).items():
                if value is None:
                    continue
                event = s.event_ticker
                raw[k][event].append(value)
                # A rising mid hurts a short maker and helps a long one, so the drift comes
                # back to the short and off the long.
                net[k][event].append(value + drift[k] if fill.maker_short else value - drift[k])
                (short if fill.maker_short else long_)[k][event].append(value)

    print(f"{n_fills:,} maker fills from real trades "
          f"({n_skipped:,} trades on strikes absent from the ladder)\n")

    by_h = {
        "net": {s.horizon: s for s in horizon_stats(net)},
        "short": {s.horizon: s for s in horizon_stats(short)},
        "long": {s.horizon: s for s in horizon_stats(long_)},
    }
    print(f"{'horizon':>8} {'markout':>10} {'net drift':>10} {'se':>8} {'t':>7} "
          f"{'short':>9} {'long':>9} {'events':>8} {'fills':>11}")
    for st in horizon_stats(raw):
        k = st.horizon
        n = by_h["net"][k]
        print(f"{k:>7}m {100 * st.mean:>9.4f}c {100 * n.mean:>9.4f}c {100 * n.se:>7.4f}c "
              f"{n.t_stat:>7.2f} {100 * by_h['short'][k].mean:>8.4f}c "
              f"{100 * by_h['long'][k].mean:>8.4f}c {st.n_events:>8,} {st.n_fills:>11,}")


if __name__ == "__main__":
    main()

"""Markout curve from real exchange trades, clustered by event.

Fills come from Kalshi's published taker_side, not the quote-rule guess (see markout_curve.py for
why that is biased). Two corrections over the naive version:

  drift   A binary's mid drifts toward its settlement value, and an in-the-money strike drifts up
          while an out-of-the-money one drifts down. A single global drift number therefore
          mis-adjusts both. The baseline here is conditional on the mid at fill time, which is the
          market's own view of moneyness. Under correct pricing this drift should be zero at every
          level, so the printed table is also a calibration check.

  size    P&L accrues per contract, not per trade. A 1-lot and a 500-lot must not weigh the same.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from ajax_pmm.analysis.ladder_bars import load_ladder_candles
from ajax_pmm.analysis.markout import BAR_SECONDS, markout_curve
from ajax_pmm.analysis.markout_stats import horizon_stats, horizon_stats_weighted
from ajax_pmm.analysis.trade_fills import fills_with_size, iter_ticker_trades

LADDER_PATH = "data/kxbtcd_ladder_candles.csv"
TRADES_PATH = "data/kxbtcd_trades.csv"
DEFAULT_HORIZONS = [1, 5, 15, 30]
N_BUCKETS = 20


def bucket(mid: float, n: int = N_BUCKETS) -> int:
    return min(int(mid * n), n - 1)


def conditional_drift(series, horizons: list[int], n: int = N_BUCKETS):
    """Mean k-minute mid change, conditional on the mid the move started from."""
    total: dict[tuple[int, int], float] = defaultdict(float)
    count: dict[tuple[int, int], int] = defaultdict(int)
    for s in series:
        bars = s.bars
        for i, b in enumerate(bars):
            if not b.priced:
                continue
            key_b = bucket(b.mid, n)
            for k in horizons:
                j = i + k
                if j >= len(bars):
                    continue
                nxt = bars[j]
                if nxt.end_ts != b.end_ts + k * BAR_SECONDS or not nxt.priced:
                    continue
                total[(k, key_b)] += nxt.mid - b.mid
                count[(k, key_b)] += 1
    return {key: total[key] / count[key] for key in total if count[key]}, count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", default=LADDER_PATH)
    ap.add_argument("--trades", default=TRADES_PATH)
    ap.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    ap.add_argument("--buckets", type=int, default=N_BUCKETS)
    args = ap.parse_args()

    series = load_ladder_candles(args.ladder)
    by_ticker = {s.ticker: s for s in series}
    print(f"{len(series):,} strikes loaded", flush=True)

    drift, dcount = conditional_drift(series, args.horizons, args.buckets)
    print(f"\nconditional 1m drift by mid at fill (should be ~0 if binaries are fairly priced):")
    print(f"{'mid':>12} {'drift':>10} {'n':>12}")
    for b in range(args.buckets):
        key = (args.horizons[0], b)
        if key in drift:
            lo = b / args.buckets
            print(f"  {lo:.2f}-{lo + 1 / args.buckets:.2f} {100 * drift[key]:>9.4f}c "
                  f"{dcount[key]:>12,}")

    raw = {k: defaultdict(list) for k in args.horizons}
    net = {k: defaultdict(list) for k in args.horizons}
    wnet = {k: defaultdict(lambda: [0.0, 0.0]) for k in args.horizons}
    n_fills = 0

    for ticker, rows in iter_ticker_trades(args.trades):
        s = by_ticker.get(ticker)
        if s is None:
            continue
        for fill, size in fills_with_size(s.bars, rows):
            n_fills += 1
            b = bucket(fill.mid_at_fill, args.buckets)
            for k, value in markout_curve(s.bars, fill, args.horizons).items():
                if value is None:
                    continue
                d = drift.get((k, b), 0.0)
                adj = value + d if fill.maker_short else value - d
                event = s.event_ticker
                raw[k][event].append(value)
                net[k][event].append(adj)
                cell = wnet[k][event]
                cell[0] += adj * size
                cell[1] += size

    print(f"\n{n_fills:,} maker fills\n")
    nets = {s.horizon: s for s in horizon_stats(net)}
    wts = {s.horizon: s for s in horizon_stats_weighted(wnet)}
    print(f"{'horizon':>8} {'raw':>10} {'drift-adj':>11} {'se':>8} {'t':>7} "
          f"{'per-CONTRACT':>14} {'se':>8} {'t':>7} {'contracts':>15}")
    for st in horizon_stats(raw):
        k, n, w = st.horizon, nets[st.horizon], wts[st.horizon]
        print(f"{k:>7}m {100 * st.mean:>9.4f}c {100 * n.mean:>10.4f}c {100 * n.se:>7.4f}c "
              f"{n.t_stat:>7.2f} {100 * w.mean:>13.4f}c {100 * w.se:>7.4f}c {w.t_stat:>7.2f} "
              f"{w.n_fills:>15,}")


if __name__ == "__main__":
    main()

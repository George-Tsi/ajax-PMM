"""Markout curve for KXBTCD passive fills, clustered by event"""

import argparse

from ajax_pmm.analysis.ladder_bars import load_ladder_candles
from ajax_pmm.analysis.markout_stats import collect_event_markouts, horizon_stats

DEFAULT_PATH = "data/kxbtcd_ladder_candles.csv"
DEFAULT_HORIZONS = [1, 5, 15, 30]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    args = ap.parse_args()

    series = load_ladder_candles(args.path)
    stats = horizon_stats(collect_event_markouts(series, args.horizons))

    events = len({s.event_ticker for s in series})
    print(f"{len(series):,} strikes across {events:,} events\n")
    print(f"{'horizon':>8} {'mean':>9} {'se':>8} {'t':>7} {'events':>8} {'fills':>10}")
    for s in stats:
        print(f"{s.horizon:>7}m {100 * s.mean:>8.4f}c {100 * s.se:>7.4f}c "
              f"{s.t_stat:>7.2f} {s.n_events:>8,} {s.n_fills:>10,}")


if __name__ == "__main__":
    main()
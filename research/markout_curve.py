"""SUPERSEDED: markout curve from quote-rule inferred fills. Output is known to be biased.

Kept because the gap between this and markout_curve_trades.py is itself the result: inferring the
fill side from bar-close quotes reports 0.5341c per fill at one minute, above the 0.5196c
half-spread that is the theoretical maximum. Signing trades against the quote at the end of the
minute selects bars where the print landed on the favourable side of where the quote settled, so
both sides come out favourably selected which no passive maker can be.

Use research/markout_curve_trades.py for any number that leaves this repo. It takes the fill side
from Kalshi's published taker_side and reports 0.0643c at the same horizon.
"""

import argparse
import sys

from ajax_pmm.analysis.ladder_bars import load_ladder_candles
from ajax_pmm.analysis.markout_stats import collect_event_markouts, horizon_stats

DEFAULT_PATH = "data/kxbtcd_ladder_candles.csv"
DEFAULT_HORIZONS = [1, 5, 15, 30]

BANNER = """
*** SUPERSEDED SCRIPT -- OUTPUT IS BIASED, DO NOT QUOTE ***
Fills here are guessed from bar-close quotes, which reports more profit per fill than the
half-spread physically allows. Use research/markout_curve_trades.py instead.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    args = ap.parse_args()

    print(BANNER, file=sys.stderr)

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
"""Pull every KXBTCD trade for the strikes in the ladder dataset, with the exchange's taker side.

Replaces the quote-rule guess in ajax_pmm.analysis.markout with Kalshi's own `taker_side`, which
is what the markout measurement actually needs and which the candle data cannot provide.

Sequential by design: parallelizing Kalshi request loops trips the rate limit and silently drops
data (2026-09-03). Resumable, because a 27,000-request pull that dies at request 25,000 with no
checkpoint is an hour thrown away.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

from ajax_pmm.kalshi.client import KalshiAPIError, KalshiClient

LADDER_PATH = "data/kxbtcd_ladder_candles.csv"
OUT_PATH = "data/kxbtcd_trades.csv"

FIELDS = ["trade_id", "ticker", "created_ts", "yes_price", "no_price", "count",
          "taker_side", "taker_book_side", "is_block_trade"]


def ladder_tickers(path: str, since_ts: int = 0) -> list[str]:
    """Strike tickers from the ladder dataset, oldest contract first.

    since_ts drops contracts that opened before the API's trade-retention cutoff, so the run
    does not spend requests on strikes that can only come back empty.
    """
    opened: dict[str, int] = {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for required in ("ticker", "open_ts"):
            if required not in (reader.fieldnames or []):
                raise ValueError(f"{path} is missing the {required!r} column")
        for row in reader:
            opened.setdefault(row["ticker"], int(row["open_ts"]))
    return sorted((t for t, ts in opened.items() if ts >= since_ts),
                  key=lambda t: (opened[t], t))


def already_pulled(path: str) -> set[str]:
    """Tickers already present in the output file, so a resumed run skips them."""
    p = Path(path)
    if not p.exists():
        return set()
    done: set[str] = set()
    with p.open(newline="") as fh:
        for row in csv.DictReader(fh):
            done.add(row["ticker"])
    return done


def pull(client: KalshiClient, writer: csv.writer, ticker: str) -> int:
    n = 0
    for t in client.iter_trades(ticker):
        writer.writerow([
            t.trade_id,
            t.ticker,
            f"{t.created_time.timestamp():.6f}",
            t.yes_price,
            t.no_price,
            t.count,
            t.taker_side,
            t.taker_book_side or "",
            int(t.is_block_trade),
        ])
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", default=LADDER_PATH)
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--limit-tickers", type=int, default=0,
                    help="stop after this many tickers (0 = all); use it to dry-run first")
    ap.add_argument("--since", default="",
                    help="skip contracts opening before this UTC date (YYYY-MM-DD)")
    ap.add_argument("--progress-every", type=int, default=200)
    args = ap.parse_args()

    since_ts = 0
    if args.since:
        since_ts = int(dt.datetime.strptime(args.since, "%Y-%m-%d")
                       .replace(tzinfo=dt.UTC).timestamp())
    tickers = ladder_tickers(args.ladder, since_ts)
    done = already_pulled(args.out)
    todo = [t for t in tickers if t not in done]
    if args.limit_tickers:
        todo = todo[:args.limit_tickers]

    print(f"{len(tickers):,} strikes in ladder, {len(done):,} already pulled, "
          f"{len(todo):,} to go", flush=True)
    if not todo:
        return

    client = KalshiClient()
    is_new = not Path(args.out).exists()
    trades = empty = 0
    failures: list[tuple[str, str]] = []
    started = time.perf_counter()

    with open(args.out, "a", newline="") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(FIELDS)
        for i, ticker in enumerate(todo, 1):
            try:
                n = pull(client, writer, ticker)
            except KalshiAPIError as exc:
                # Never swallow these: a silently dropped ticker is how the 2026-09-03
                # parallelization bug lost 40% of matched events without any error surfacing.
                failures.append((ticker, str(exc)[:120]))
                print(f"  FAILED {ticker}: {exc}", file=sys.stderr, flush=True)
                continue
            trades += n
            empty += n == 0
            fh.flush()
            if i % args.progress_every == 0 or i == len(todo):
                elapsed = time.perf_counter() - started
                rate = i / elapsed
                print(f"  {i:>6,}/{len(todo):,} strikes  {trades:>10,} trades  "
                      f"{rate:5.1f} strikes/s  eta {(len(todo) - i) / rate / 60:5.1f} min",
                      flush=True)

    elapsed = time.perf_counter() - started
    print(f"\n{trades:,} trades from {len(todo) - len(failures):,} strikes in {elapsed / 60:.1f} min")
    print(f"{empty:,} strikes returned no trades (expected past the ~67-day retention cutoff)")
    if failures:
        print(f"{len(failures):,} strikes FAILED and were not written:", file=sys.stderr)
        for ticker, err in failures[:20]:
            print(f"  {ticker}: {err}", file=sys.stderr)
        print("Re-run to retry them; completed strikes are skipped automatically.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

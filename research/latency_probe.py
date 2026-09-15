"""Latency probe: time origin-bound Kalshi requests from one host.

Run on home and us-east-1 at the same time with the same ticker. Samples land on whole-second
boundaries, so the two hosts interleave without coordinating. Alternates the uncached orderbook 
against the edge-cached status endpoint; the gap between them is the edge -> origin leg."""

import argparse
import csv
import time

import requests

BOOK = "https://api.elections.kalshi.com/trade-api/v2/markets/{}/orderbook"
STATUS = "https://api.elections.kalshi.com/trade-api/v2/exchange/status"


def sample(session, url):
    t0 = time.perf_counter()
    try:
        r = session.get(url, timeout=10)
    except requests.RequestException as e:
        return None, "", "", type(e).__name__
    return time.perf_counter() - t0, r.headers.get("X-Amz-Cf-Pop", ""), \
        r.headers.get("X-Cache", ""), r.status_code


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--host", required=True, help="label: home or us-east-1")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--period", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    book = BOOK.format(args.ticker)
    session = requests.Session()
    sample(session, book)

    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["host", "ts", "endpoint", "rtt_s", "pop", "cache", "status"])
        for i in range(args.n):
            time.sleep(-time.time() % args.period)
            url, name = (book, "orderbook") if i % 2 == 0 else (STATUS, "status")
            rtt, pop, cache, status = sample(session, url)
            w.writerow([args.host, f"{time.time():.4f}", name,
                        "" if rtt is None else f"{rtt:.6f}", pop, cache, status])
            if i % 50 == 0:
                fh.flush()

if __name__ == "__main__":
    main()
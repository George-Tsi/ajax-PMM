"""Compare latency probe runs across hosts.

Two views. The marginal distribution per (host, endpoint) is the readable one; the paired
difference is the one that decides the colocation question. Server-side response time moves with
volatility and time of day by more than the effect being measured, so comparing two runs as whole
distributions can report a difference that is really just a difference in when they ran. The probe
samples on whole-second boundaries precisely so the same second can be matched across hosts.

Status-endpoint rows are filtered to cache hits: a miss there took an origin round trip and is not
the edge-only measurement the decomposition needs.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict

ENDPOINTS = ("orderbook", "status")


def quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(int(q * len(s)), len(s) - 1)]


def load(paths: list[str]) -> list[dict]:
    rows = []
    for path in paths:
        with open(path, newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csvs", nargs="+", help="one probe CSV per host")
    ap.add_argument("--threshold-ms", type=float, default=10.0,
                    help="paired p50 gain below which contingency #2 is dead")
    args = ap.parse_args()

    rows = load(args.csvs)
    rtt: dict[tuple[str, str], list[float]] = defaultdict(list)
    paired: dict[tuple[str, str, int], float] = {}
    errors: dict[str, int] = defaultdict(int)
    pops: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        host, endpoint = r["host"], r["endpoint"]
        if not r["rtt_s"]:
            errors[host] += 1
            continue
        if endpoint == "status" and "Hit" not in r["cache"]:
            continue
        if r["status"] != "200":
            errors[host] += 1
            continue
        value = float(r["rtt_s"]) * 1000
        rtt[(host, endpoint)].append(value)
        pops[host].add(r["pop"])
        paired[(host, endpoint, int(float(r["ts"])))] = value

    hosts = sorted({h for h, _ in rtt})

    for host in hosts:
        if len(pops[host]) > 1:
            print(f"WARNING {host} hit multiple PoPs {sorted(pops[host])}; "
                  f"the run is not one experiment")
        if errors[host]:
            print(f"WARNING {host} had {errors[host]} failed samples")

    print(f"\n{'host':<12} {'endpoint':<11} {'n':>7} {'p50':>9} {'p90':>9} {'p99':>9}")
    for host in hosts:
        for endpoint in ENDPOINTS:
            xs = rtt.get((host, endpoint))
            if not xs:
                continue
            print(f"{host:<12} {endpoint:<11} {len(xs):>7,} {quantile(xs, .50):>7.2f}ms "
                  f"{quantile(xs, .90):>7.2f}ms {quantile(xs, .99):>7.2f}ms")

    print(f"\nedge->origin leg (orderbook p50 - status p50), diagnostic only:")
    for host in hosts:
        book, status = rtt.get((host, "orderbook")), rtt.get((host, "status"))
        if book and status:
            print(f"  {host:<12} {quantile(book, .50) - quantile(status, .50):>7.2f}ms")

    if len(hosts) < 2:
        print("\nonly one host present; the paired comparison needs both arms")
        return

    base, other = hosts[0], hosts[1]
    for endpoint in ENDPOINTS:
        seconds = {s for h, e, s in paired if e == endpoint and h == base}
        seconds &= {s for h, e, s in paired if e == endpoint and h == other}
        diffs = [paired[(base, endpoint, s)] - paired[(other, endpoint, s)] for s in seconds]
        if not diffs:
            print(f"\n{endpoint}: no shared seconds; the arms did not overlap in time")
            continue
        p50 = quantile(diffs, .50)
        print(f"\n{endpoint}: {len(diffs):,} paired seconds, "
              f"{base} slower than {other} by p50 {p50:.2f}ms "
              f"(p90 {quantile(diffs, .90):.2f}ms)")
        if endpoint == "orderbook":
            verdict = "LIVE" if p50 >= args.threshold_ms else "DEAD"
            print(f"  contingency #2 is {verdict} against the {args.threshold_ms:.0f}ms threshold")


if __name__ == "__main__":
    main()

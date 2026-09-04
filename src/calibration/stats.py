"""Shared calibration-bucketing logic for research scripts."""

from __future__ import annotations

from collections import defaultdict


def bucket_index(price: float, n_buckets: int) -> int:
    return min(int(price * n_buckets), n_buckets - 1)


def calibration_table(pairs: list[tuple[float, str]], n_buckets: int) -> list[dict]:
    sums = defaultdict(lambda: {"n": 0, "implied_sum": 0.0, "realized_sum": 0})
    for implied, result in pairs:
        b = bucket_index(implied, n_buckets)
        realized = 1 if result == "yes" else 0
        sums[b]["n"] += 1
        sums[b]["implied_sum"] += implied
        sums[b]["realized_sum"] += realized

    table = []
    for b in range(n_buckets):
        s = sums[b]
        if s["n"] == 0:
            continue
        table.append({
            "bucket": b,
            "n": s["n"],
            "mean_implied": s["implied_sum"] / s["n"],
            "realized_rate": s["realized_sum"] / s["n"],
        })
    return table


def print_calibration_table(
    pairs: list[tuple[float, str]],
    n_buckets: int,
    label: str | None = None,
    n_width: int = 4,
) -> None:
    if label is not None:
        print(f"\n--- {label} ---")
    for row in calibration_table(pairs, n_buckets):
        gap = row["realized_rate"] - row["mean_implied"]
        print(f"bucket {row['bucket']}: n={row['n']:>{n_width}} implied={row['mean_implied']:.3f} "
              f"realized={row['realized_rate']:.3f} gap={gap:+.3f}")

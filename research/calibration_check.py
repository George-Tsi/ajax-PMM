"""Check whether Kalshi's implied prbabilities were calibrated against realized BTC outcomes.

Buckets settled KXBTCD markets by last traded price (Kalshi's implied YES probability) and compares each bucket's realized win rate against its mean implied probability.
A well-calibrated market has realized ~= implied in every bucket."""


from __future__ import annotations
from pathlib import Path
import csv
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SETTLED_CSV = DATA_DIR / "kxbtcd_settled_20260825_0346.csv"
IN_BUCKETS = 10

def load_traded_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if float(row["volume"]) <= 0:
                continue
            rows.append(row)
    return rows 

def bucket_index(price: float, n_buckets: int) -> int:
    return min(int(price * n_buckets), n_buckets - 1)

def calibration_table(rows: list[dict], n_buckets: int) -> list[dict]:
    sums = defaultdict(lambda: {"n": 0, "implied_sum": 0.0, "realized_sum": 0})
    for row in rows:
        price = float(row["last_price"])
        b = bucket_index(price, n_buckets)
        realized = 1 if row["result"] == "yes" else 0
        sums[b]["n"] += 1
        sums[b]["implied_sum"] += price
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

def main() -> None:
    rows = load_traded_rows(SETTLED_CSV)
    table = calibration_table(rows, IN_BUCKETS)
    for row in table:
        gap = row["realized_rate"] - row["mean_implied"]
        print(f"bucket {row['bucket']}: n={row['n']:>6} implied={row['mean_implied']:.3f} "
              f"realized={row['realized_rate']:.3f} gap={gap:+.3f}")

if __name__ == "__main__":
    main()
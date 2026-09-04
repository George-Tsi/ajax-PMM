"""Check whether Kalshi's implied prbabilities were calibrated against realized BTC outcomes.

Buckets settled KXBTCD markets by last traded price (Kalshi's implied YES probability) and compares each bucket's realized win rate against its mean implied probability.
A well-calibrated market has realized ~= implied in every bucket."""


from __future__ import annotations
from pathlib import Path
import csv

from src.calibration.stats import print_calibration_table

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

def main() -> None:
    rows = load_traded_rows(SETTLED_CSV)
    pairs = [(float(row["last_price"]), row["result"]) for row in rows]
    print_calibration_table(pairs, IN_BUCKETS, n_width=6)

if __name__ == "__main__":
    main()
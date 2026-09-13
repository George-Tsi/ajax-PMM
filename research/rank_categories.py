"""Rank Kalshi's open-market categories by realized trading volume.

Validates the Phase 1 category hypothesis (BTC/weather/politics) against
live data before it gets locked in DECISIONS.md.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ajax_pmm.kalshi.client import KalshiClient

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIELDNAMES = ["category", "events", "markets", "volume_24h", "volume_total", "open_interest"]


def rank_by_category() -> list[dict]:
    client = KalshiClient()
    volume_24h: dict[str, float] = defaultdict(float)
    volume_total: dict[str, float] = defaultdict(float)
    open_interest: dict[str, float] = defaultdict(float)
    n_events: dict[str, int] = defaultdict(int)
    n_markets: dict[str, int] = defaultdict(int)

    for event in client.iter_events(status="open"):
        cat = event.category
        volume_24h[cat] += event.volume_24h
        volume_total[cat] += event.volume
        open_interest[cat] += event.open_interest
        n_events[cat] += 1
        n_markets[cat] += len(event.markets)

    rows = [
        {
            "category": cat,
            "events": n_events[cat],
            "markets": n_markets[cat],
            "volume_24h": round(volume_24h[cat], 2),
            "volume_total": round(volume_total[cat], 2),
            "open_interest": round(open_interest[cat], 2),
        }
        for cat in volume_24h
    ]
    rows.sort(key=lambda r: r["volume_24h"], reverse=True)
    return rows


def print_table(rows: list[dict]) -> None:
    header = f"{'category':<24}{'events':>8}{'markets':>9}{'vol_24h':>14}{'vol_total':>16}{'open_int':>14}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['category']:<24}{r['events']:>8}{r['markets']:>9}"
            f"{r['volume_24h']:>14,.0f}{r['volume_total']:>16,.0f}{r['open_interest']:>14,.0f}"
        )


def save_csv(rows: list[dict]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"category_volume_{datetime.now(timezone.utc):%Y%m%d}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


if __name__ == "__main__":
    rows = rank_by_category()
    print_table(rows)
    out_path = save_csv(rows)
    print(f"\nsaved to {out_path}")

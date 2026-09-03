"""Pull the full settled history of Kalshi's hourly BTC ladder markets (KXBTCD).

Each event is one hourly strike ladder; each market within it is one strike's
binary outcome. This gives strike, realized settlement value, and outcome for
every settled instance, straight from /events - no candlestick/trade pulls
needed for a first calibration dataset.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from kalshi.client import KalshiClient

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SERIES_TICKER = "KXBTCD"
FIELDNAMES = [
    "event_ticker",
    "ticker",
    "open_time",
    "close_time",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "result",
    "expiration_value",
    "last_price",
    "volume",
    "open_interest",
]


def pull_rows() -> list[dict]:
    client = KalshiClient()
    rows = []
    for event in client.iter_events(status="settled", series_ticker=SERIES_TICKER):
        for m in event.markets:
            rows.append(
                {
                    "event_ticker": event.event_ticker,
                    "ticker": m.ticker,
                    "open_time": m.open_time.isoformat() if m.open_time else "",
                    "close_time": m.close_time.isoformat() if m.close_time else "",
                    "strike_type": m.strike_type or "",
                    "floor_strike": m.floor_strike if m.floor_strike is not None else "",
                    "cap_strike": m.cap_strike if m.cap_strike is not None else "",
                    "result": m.result or "",
                    "expiration_value": m.expiration_value if m.expiration_value is not None else "",
                    "last_price": m.last_price if m.last_price is not None else "",
                    "volume": m.volume,
                    "open_interest": m.open_interest,
                }
            )
    return rows


def save_csv(rows: list[dict]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"kxbtcd_settled_{datetime.now(timezone.utc):%Y%m%d_%H%M}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


if __name__ == "__main__":
    rows = pull_rows()
    print(f"pulled {len(rows)} settled markets across KXBTCD events")
    if rows:
        close_times = sorted(r["close_time"] for r in rows if r["close_time"])
        results = {r["result"] for r in rows}
        print(f"close_time range: {close_times[0]} -> {close_times[-1]}")
        print(f"distinct results: {results}")
    out_path = save_csv(rows)
    print(f"saved to {out_path}")

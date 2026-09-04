"""Fetch/cache Coinbase candle history and look up spot price at an arbitrary timestamp."""

from __future__ import annotations

import csv
from bisect import bisect_left
from pathlib import Path

from src.coinbase.client import Candle, CoinbaseClient


def save_candles(path: Path, candles: list[Candle]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "low", "high", "open", "close", "volume"])
        for c in candles:
            writer.writerow([c.ts, c.low, c.high, c.open, c.close, c.volume])


def load_cached_candles(path: Path) -> list[Candle]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(Candle(
                ts=int(row["ts"]),
                low=float(row["low"]),
                high=float(row["high"]),
                open=float(row["open"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
        ))
    return out


def fetch_price_history(client: CoinbaseClient, cache_path: Path, product_id: str, start_ts: int, end_ts: int) -> list[Candle]:
    if cache_path.exists():
        return load_cached_candles(cache_path)
    candles = client.get_candles(product_id, start_ts, end_ts)
    save_candles(cache_path, candles)
    return candles


def build_price_lookup(candles: list[Candle]) -> tuple[list[int], list[float]]:
    ordered = sorted(candles, key=lambda c: c.ts)
    timestamps = [c.ts for c in ordered]
    closes = [c.close for c in ordered]
    return timestamps, closes


def price_at(timestamps: list[int], closes: list[float], ts: int) -> float:
    i = bisect_left(timestamps, ts)
    if i == 0:
        return closes[0]
    if i == len(timestamps):
        return closes[-1]
    before, after = timestamps[i - 1], timestamps[i]
    return closes[i - 1] if (ts - before) <= (after - ts) else closes[i]

"""Public (unauthenticated) REST client for Coinbase Exchange's historical candles."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import requests

BASE_URL = "https://api.exchange.coinbase.com"
DEFAULT_TIMEOUT_S = 10.0
MAX_RETRIES = 3
RETRY_BACKOFF = 0.5
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
MAX_CANDLES_PER_CALL = 300 # Coinbase caps one /candles request to 300 rows. At 1-minute bars, that equivalates to 300 min --> 5 hours. Need to chunk into 5 hour blocks
GRANULARITY_S = 60


class CoinbaseAPIError(RuntimeError):
    pass

# /candles endpoint returns each bar as a bare list, not a JSON object. Wrap it in dataclass with a from_row constructor.

@dataclass(frozen=True)
class Candle:
    ts: int
    low: float
    high: float
    open: float
    close: float
    volume: float

    @classmethod
    def from_row(cls, row: list) -> "Candle":
        ts, low, high, open_, close, volume = row
        return cls(ts=ts, low=low, high=high, open=open_, close=close, volume= volume) # not OHLC order


class CoinbaseClient:
    """Thin wrapper over Coinbase Exchange's public candles endpoint."""

    def __init__(
            self, base_url: str = BASE_URL,
            timeout_s: float = DEFAULT_TIMEOUT_S,
            session: requests.Session | None = None
    ) -> None:
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._session = session or requests.Session()

    def _get(self, path: str, params: dict) -> list:
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                time.sleep(RETRY_BACKOFF * attempt)
            try: 
                resp = self._session.get(url, params=params, timeout=self._timeout_s)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code not in RETRY_STATUS_CODES:
                raise CoinbaseAPIError(f"GET {path} -> {resp.status_code}")
        raise CoinbaseAPIError(f"GET {path} failed after {MAX_RETRIES} attempts") from last_error


# To call every 1-minute BTC candle between start_ts and end_ts

    def get_candles(self, product_id: str, start_ts: int, end_ts: int) -> list[Candle]:
        """Fetch 1-minute OHLCV candles, chunking requests under Coinbase's 300-row cap."""
        window_s = MAX_CANDLES_PER_CALL * GRANULARITY_S
        out: list[Candle] = []
        chunk_start = start_ts
        while chunk_start < end_ts:
            chunk_end = min(chunk_start + window_s, end_ts)
            params = {
                "granularity": GRANULARITY_S,
                "start": datetime.fromtimestamp(chunk_start, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(chunk_end, tz=timezone.utc).isoformat()
            }
            rows = self._get(f"/products/{product_id}/candles", params)
            out.extend(Candle.from_row(r) for r in rows)
            chunk_start = chunk_end
        return out
"""Public (unauthenticated) REST client for Kalshi's Trade API v2."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_TIMEOUT_S = 10.0
MAX_RETRIES = 3
RETRY_BACKOFF_S = 0.5
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
MAX_CANDLESTICKS_PER_CALL = 5000


class KalshiAPIError(RuntimeError):
    pass


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _parse_float(raw: str | float | None) -> float | None:
    if raw in (None, ""):
        return None
    return float(raw)


@dataclass(frozen=True)
class Market:
    ticker: str
    status: str
    volume: float
    volume_24h: float
    open_interest: float
    open_time: datetime | None
    close_time: datetime | None
    strike_type: str | None
    floor_strike: float | None
    cap_strike: float | None
    result: str | None
    expiration_value: float | None
    last_price: float | None

    @classmethod
    def from_json(cls, raw: dict) -> "Market":
        return cls(
            ticker=raw["ticker"],
            status=raw["status"],
            volume=float(raw.get("volume_fp", 0.0)),
            volume_24h=float(raw.get("volume_24h_fp", 0.0)),
            open_interest=float(raw.get("open_interest_fp", 0.0)),
            open_time=_parse_ts(raw.get("open_time")),
            close_time=_parse_ts(raw.get("close_time")),
            strike_type=raw.get("strike_type"),
            floor_strike=raw.get("floor_strike"),
            cap_strike=raw.get("cap_strike"),
            result=raw.get("result") or None,
            expiration_value=_parse_float(raw.get("expiration_value")),
            last_price=_parse_float(raw.get("last_price_dollars")),
        )


@dataclass(frozen=True)
class Event:
    event_ticker: str
    series_ticker: str
    category: str
    markets: tuple[Market, ...] = field(default_factory=tuple)

    @classmethod
    def from_json(cls, raw: dict) -> "Event":
        return cls(
            event_ticker=raw["event_ticker"],
            series_ticker=raw.get("series_ticker", ""),
            category=raw.get("category") or "Unknown",
            markets=tuple(Market.from_json(m) for m in raw.get("markets", [])),
        )

    @property
    def volume(self) -> float:
        return sum(m.volume for m in self.markets)

    @property
    def volume_24h(self) -> float:
        return sum(m.volume_24h for m in self.markets)

    @property
    def open_interest(self) -> float:
        return sum(m.open_interest for m in self.markets)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    ticker: str
    created_time: datetime
    yes_price: float
    no_price: float
    count: float
    taker_side: str

    @classmethod
    def from_json(cls, raw: dict) -> "Trade":
        return cls(
            trade_id=raw["trade_id"],
            ticker=raw["ticker"],
            created_time=_parse_ts(raw["created_time"]),
            yes_price=float(raw["yes_price_dollars"]),
            no_price=float(raw["no_price_dollars"]),
            count=float(raw.get("count_fp", 0.0)),
            taker_side=raw["taker_side"],
        )


@dataclass(frozen=True)
class Candlestick:
    end_ts: int
    open_interest: float
    volume: float
    last_price: float
    yes_bid_open: float
    yes_bid_high: float
    yes_bid_low: float
    yes_bid_close: float
    yes_ask_open: float
    yes_ask_high: float
    yes_ask_low: float
    yes_ask_close: float

    @classmethod
    def from_json(cls, raw: dict) -> "Candlestick":
        bid, ask = raw["yes_bid"], raw["yes_ask"]
        return cls(
            end_ts=raw["end_period_ts"],
            open_interest=float(raw.get("open_interest_fp", 0.0)),
            volume=float(raw.get("volume_fp", 0.0)),
            last_price=float(raw.get("price", {}).get("previous_dollars") or 0.0),
            yes_bid_open=float(bid["open_dollars"]),
            yes_bid_high=float(bid["high_dollars"]),
            yes_bid_low=float(bid["low_dollars"]),
            yes_bid_close=float(bid["close_dollars"]),
            yes_ask_open=float(ask["open_dollars"]),
            yes_ask_high=float(ask["high_dollars"]),
            yes_ask_low=float(ask["low_dollars"]),
            yes_ask_close=float(ask["close_dollars"]),
        )


class KalshiClient:
    """Thin wrapper over Kalshi's public market-data endpoints."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._session = session or requests.Session()

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                time.sleep(RETRY_BACKOFF_S * attempt)
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout_s)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code not in RETRY_STATUS_CODES:
                raise KalshiAPIError(f"GET {path} -> {resp.status_code}: {resp.text[:200]}")
            last_error = KalshiAPIError(f"GET {path} -> {resp.status_code}")
        raise KalshiAPIError(f"GET {path} failed after {MAX_RETRIES} attempts") from last_error

    def iter_events(
        self,
        status: str = "open",
        series_ticker: str | None = None,
        limit: int = 200,
        with_nested_markets: bool = True,
    ) -> Iterator[Event]:
        """Page through /events, yielding one Event (with nested markets) at a time."""
        cursor: str | None = None
        while True:
            params = {
                "limit": limit,
                "status": status,
                "with_nested_markets": str(with_nested_markets).lower(),
            }
            if series_ticker:
                params["series_ticker"] = series_ticker
            if cursor:
                params["cursor"] = cursor
            page = self._get("/events", params)
            for raw in page["events"]:
                yield Event.from_json(raw)
            cursor = page.get("cursor")
            if not cursor:
                return

    def iter_trades(
        self,
        ticker: str,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int = 1000,
    ) -> Iterator[Trade]:
        """Page through /markets/trades for one ticker, newest first.

        Trades arrive newest-first, so once a page drops below min_ts we stop
        paginating rather than walking the rest of the ticker's full history.
        """
        cursor: str | None = None
        while True:
            params: dict = {"ticker": ticker, "limit": limit}
            if min_ts is not None:
                params["min_ts"] = min_ts
            if max_ts is not None:
                params["max_ts"] = max_ts
            if cursor:
                params["cursor"] = cursor
            page = self._get("/markets/trades", params)
            trades = page["trades"]
            if not trades:
                return
            for raw in trades:
                trade = Trade.from_json(raw)
                trade_ts = trade.created_time.timestamp()
                if min_ts is not None and trade_ts < min_ts:
                    return
                if max_ts is not None and trade_ts > max_ts:
                    continue
                yield trade
            cursor = page.get("cursor")
            if not cursor:
                return

    def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 1,
    ) -> list[Candlestick]:
        """Fetch minute/hour/day OHLC bars, chunking requests under the 5000-bar cap."""
        window_s = MAX_CANDLESTICKS_PER_CALL * period_interval * 60
        out: list[Candlestick] = []
        chunk_start = start_ts
        while chunk_start < end_ts:
            chunk_end = min(chunk_start + window_s, end_ts)
            params = {
                "start_ts": chunk_start,
                "end_ts": chunk_end,
                "period_interval": period_interval,
            }
            page = self._get(f"/series/{series_ticker}/markets/{ticker}/candlesticks", params)
            out.extend(Candlestick.from_json(c) for c in page["candlesticks"])
            chunk_start = chunk_end
        return out

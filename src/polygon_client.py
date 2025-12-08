from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
import websockets
from dateutil import tz
import pytz

from config import API_KEY, WS_RECONNECT_DELAY_SECONDS
from src.data_models import Candle, CandleSeries


logger = logging.getLogger(__name__)


class PolygonClient:
    """Polygon.io REST and WebSocket client for delayed stock data.

    Provides REST helpers for details, snapshots, previous day, and aggregate ranges,
    and a WebSocket streamer that emits trade prints for a single ticker.
    """

    REST_BASE: str = "https://api.polygon.io"
    WS_URL: str = "wss://socket.polygon.io/stocks"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.Client(timeout=20.0)

    # ---------------------- REST METHODS ----------------------
    def get_ticker_details(self, ticker: str) -> Dict[str, Any]:
        url = f"{self.REST_BASE}/v3/reference/tickers/{ticker.upper()}"
        params = {"apiKey": self.api_key}
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def get_previous_close(self, ticker: str) -> Dict[str, Any]:
        url = f"{self.REST_BASE}/v2/aggs/ticker/{ticker.upper()}/prev"
        params = {"adjusted": "true", "apiKey": self.api_key}
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        url = f"{self.REST_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
        params = {"apiKey": self.api_key}
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def get_daily_aggs_range(self, ticker: str, start_date: str, end_date: str) -> Dict[str, Any]:
        url = (
            f"{self.REST_BASE}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start_date}/{end_date}"
        )
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key}
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def get_aggs_range(self, ticker: str, mult: int, unit: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Generic aggregates range endpoint for different granularities.

        unit: one of 'minute', 'hour', 'day', 'week', 'month', etc.
        Dates should be ISO-8601 (YYYY-MM-DD or full timestamps for intraday windows).
        """
        url = (
            f"{self.REST_BASE}/v2/aggs/ticker/{ticker.upper()}/range/{mult}/{unit}/{start_date}/{end_date}"
        )
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key}
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    # ---------------------- UTILITIES ----------------------
    @staticmethod
    def to_utc_datetime(ts_ms: int) -> datetime:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

    @staticmethod
    def et_now_status(dt_utc: Optional[datetime] = None) -> str:
        """Heuristic market status string based on ET time.

        Returns one of: PRE-MARKET, MARKET HOURS, AFTER-HOURS, CLOSED
        """
        eastern = tz.gettz("US/Eastern")
        now = dt_utc or datetime.now(timezone.utc)
        now_et = now.astimezone(eastern)
        if now_et.weekday() >= 5:  # weekend
            return "CLOSED"
        open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et < open_time:
            return "PRE-MARKET"
        if open_time <= now_et <= close_time:
            return "MARKET HOURS"
        if now_et > close_time:
            return "AFTER-HOURS"
        return "CLOSED"

    def parse_agg_candles(self, agg_json: Dict[str, Any]) -> CandleSeries:
        results = agg_json.get("results") or []
        candles: List[Candle] = []
        for r in results:
            try:
                candles.append(
                    Candle(
                        t=int(r.get("t")),
                        o=float(r.get("o")),
                        h=float(r.get("h")),
                        l=float(r.get("l")),
                        c=float(r.get("c")),
                        v=float(r.get("v")),
                    )
                )
            except Exception as exc:
                logger.debug("Skipping malformed candle: %s (%s)", r, exc)
        return CandleSeries(candles=candles)

    def fetch_trades_today(self, ticker: str) -> List[dict]:
        """Return today's trades since 09:30 ET, paginating through Polygon's cursor."""
        try:
            eastern = pytz.timezone("America/New_York")
            et_now = datetime.now(eastern)
            market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
            if et_now.hour < 9 or (et_now.hour == 9 and et_now.minute < 30):
                market_open = market_open - timedelta(days=1)
            start_ms = int(market_open.timestamp() * 1000)
            trades: List[dict] = []
            url = f"{self.REST_BASE}/v3/trades/{ticker.upper()}"
            params: Dict[str, Any] = {
                "timestamp.gte": start_ms,
                "limit": 1000,
                "sort": "timestamp",
                "order": "asc",
                "apiKey": self.api_key,
            }
            pages = 0
            max_pages = 10  # safety to avoid runaway pagination
            while url and pages < max_pages:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                for item in data.get("results", []):
                    trades.append(
                        {
                            "timestamp": item.get("sip_timestamp") or item.get("timestamp") or item.get("t"),
                            "price": item.get("price"),
                            "size": item.get("size"),
                            "exchange": item.get("exchange") or item.get("x"),
                        }
                    )
                if len(trades) >= 5000:
                    break
                next_url = data.get("next_url")
                if not next_url:
                    break
                url = next_url
                params = {"apiKey": self.api_key}
                pages += 1
            return trades
        except Exception as exc:  # pragma: no cover - network
            logger.error("Failed to fetch trades for %s: %s", ticker, exc)
            return []


    def fetch_quotes_range(self, ticker: str, start_dt: datetime, end_dt: datetime) -> List[dict]:
        """Return quotes between start_dt and end_dt."""
        try:
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            url = f"{self.REST_BASE}/v3/quotes/{ticker.upper()}"
            params = {
                "timestamp.gte": start_ms,
                "timestamp.lte": end_ms,
                "limit": 5000,
                "sort": "timestamp",
                "order": "asc",
                "apiKey": self.api_key,
            }
            response = self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            quotes: List[dict] = []
            for item in data.get("results", []):
                quotes.append(
                    {
                        "timestamp": item.get("sip_timestamp") or item.get("timestamp") or item.get("t"),
                        "bid": item.get("bid_price"),
                        "ask": item.get("ask_price"),
                        "bid_size": item.get("bid_size"),
                        "ask_size": item.get("ask_size"),
                    }
                )
            return quotes
        except Exception as exc:  # pragma: no cover - network
            logger.error("Failed to fetch quotes for %s: %s", ticker, exc)
            return []

    # ---------------------- WEBSOCKET STREAM ----------------------
    async def stream_ticker(
        self,
        ticker: str,
        on_data: Callable[[Dict[str, Any]], None],
        on_status: Callable[[str], None],
        stop_event: asyncio.Event,
    ) -> None:
        """Stream trade prints for a ticker using Polygon's delayed T.* channel.

        - Emits status transitions: CONNECTING -> CONNECTED -> DELAYED (first data)
        - On disconnects, emits RECONNECTING and attempts reconnect with backoff.
        - Stops when `stop_event` is set.
        """
        sub = f"T.{ticker.upper()}"
        first_event_seen = False

        async def _auth_and_sub(ws) -> None:
            await ws.send(json.dumps({"action": "auth", "params": self.api_key}))
            await ws.send(json.dumps({"action": "subscribe", "params": sub}))

        while not stop_event.is_set():
            try:
                on_status("CONNECTING")
                async with websockets.connect(self.WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    on_status("CONNECTED")
                    await _auth_and_sub(ws)

                    async for msg in ws:
                        if stop_event.is_set():
                            break
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue

                        # Polygon can send lists of events
                        events = data if isinstance(data, list) else [data]
                        for ev in events:
                            ev_type = ev.get("ev") or ev.get("eventType")
                            if ev_type == "status":
                                # Handle status messages if needed
                                # E.g. {"ev":"status","status":"auth_success"}
                                continue
                            if ev_type == "T":  # trade event
                                if not first_event_seen:
                                    first_event_seen = True
                                    on_status("DELAYED")
                                on_data(ev)
                    # graceful end of stream (server closed)
            except Exception as exc:
                logger.warning("WebSocket error: %s", exc)
                if stop_event.is_set():
                    break
                try:
                    on_status("ERROR")
                except Exception:
                    pass
                on_status("RECONNECTING")
                await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

        try:
            on_status("DISCONNECTED")
        except Exception:
            pass

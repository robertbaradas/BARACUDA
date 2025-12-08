from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.data_models import Candle, CandleSeries, CompanyDetails, DailyStats
from src.polygon_client import PolygonClient

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached value with expiration timestamp."""
    data: Any
    expires_at: float


class MarketDataService:
    """Service layer for market data with TTL-based caching."""

    # Cache TTLs in seconds
    TTL_SNAPSHOT = 15       # Price data changes frequently
    TTL_DETAILS = 3600      # Company info rarely changes
    TTL_PREV_CLOSE = 3600   # Fixed after market close
    TTL_CANDLES = 300       # Historical data, 5 min cache
    TTL_TRADES = 60         # Recent trades

    def __init__(self, client: PolygonClient):
        self.client = client
        self._cache: Dict[str, CacheEntry] = {}

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.data

    def _set_cached(self, key: str, data: Any, ttl: float) -> None:
        """Store value in cache with TTL."""
        self._cache[key] = CacheEntry(data=data, expires_at=time.time() + ttl)

    def clear_cache(self, ticker: Optional[str] = None) -> None:
        """Clear cache entirely or for a specific ticker."""
        if ticker is None:
            self._cache.clear()
        else:
            ticker_upper = ticker.upper()
            keys_to_remove = [k for k in self._cache if k.startswith(f"{ticker_upper}:")]
            for k in keys_to_remove:
                del self._cache[k]

    def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        """Get current snapshot with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:snapshot"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s snapshot", ticker)
            return cached

        logger.debug("Fetching snapshot for %s", ticker)
        data = self.client.get_snapshot(ticker)
        self._set_cached(key, data, self.TTL_SNAPSHOT)
        return data

    def get_ticker_details(self, ticker: str) -> Dict[str, Any]:
        """Get company details with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:details"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s details", ticker)
            return cached

        logger.debug("Fetching details for %s", ticker)
        data = self.client.get_ticker_details(ticker)
        self._set_cached(key, data, self.TTL_DETAILS)
        return data

    def get_previous_close(self, ticker: str) -> Dict[str, Any]:
        """Get previous close with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:prev_close"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s prev_close", ticker)
            return cached

        logger.debug("Fetching prev_close for %s", ticker)
        data = self.client.get_previous_close(ticker)
        self._set_cached(key, data, self.TTL_PREV_CLOSE)
        return data

    def get_daily_aggs_range(self, ticker: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get daily aggregates with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:daily:{start_date}:{end_date}"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s daily aggs", ticker)
            return cached

        logger.debug("Fetching daily aggs for %s", ticker)
        data = self.client.get_daily_aggs_range(ticker, start_date, end_date)
        self._set_cached(key, data, self.TTL_CANDLES)
        return data

    def get_aggs_range(
        self, ticker: str, mult: int, unit: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Get aggregates for any timeframe with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:aggs:{mult}:{unit}:{start_date}:{end_date}"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s aggs", ticker)
            return cached

        logger.debug("Fetching aggs for %s", ticker)
        data = self.client.get_aggs_range(ticker, mult, unit, start_date, end_date)
        self._set_cached(key, data, self.TTL_CANDLES)
        return data

    def fetch_trades_today(self, ticker: str) -> List[dict]:
        """Get today's trades with caching."""
        ticker = ticker.upper()
        key = f"{ticker}:trades_today"

        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("Cache hit for %s trades", ticker)
            return cached

        logger.debug("Fetching trades for %s", ticker)
        data = self.client.fetch_trades_today(ticker)
        self._set_cached(key, data, self.TTL_TRADES)
        return data

    def parse_candles(self, agg_json: Dict[str, Any]) -> CandleSeries:
        """Parse aggregates response into CandleSeries (delegates to client)."""
        return self.client.parse_agg_candles(agg_json)

    @staticmethod
    def get_market_status() -> str:
        """Get current market status string."""
        return PolygonClient.et_now_status()

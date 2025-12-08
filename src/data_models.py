from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class CompanyDetails:
    """Minimal subset of company details used in the UI."""

    ticker: str
    name: Optional[str]
    description: Optional[str]
    market_cap: Optional[float]
    pe_ratio: Optional[float]


@dataclass
class DailyStats:
    """Daily statistics and prior close for the instrument."""

    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[int]
    prev_close: Optional[float]
    last_trade_price: Optional[float]
    last_trade_time_utc: Optional[datetime]


@dataclass
class LiveQuote:
    """Level 1 quote fields from snapshot polling (bid/ask)."""

    bid: Optional[float]
    ask: Optional[float]
    bid_size: Optional[int]
    ask_size: Optional[int]


@dataclass
class RollingStats:
    """Rolling statistics computed from aggregates.

    - avg_volume_30d
    - 52-week high/low
    """

    avg_volume_30d: Optional[float]
    week_52_high: Optional[float]
    week_52_low: Optional[float]


@dataclass
class Candle:
    t: int  # ms epoch
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class CandleSeries:
    candles: List[Candle]


@dataclass
class Account:
    """Trading account (paper trading portfolio)."""

    id: str
    user_id: str
    name: str
    base_ccy: str = "USD"
    starting_cash: float = 10000.0
    cash: float = 10000.0
    equity: float = 10000.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Order:
    """Order record."""

    id: str
    account_id: str
    ticker: str
    side: str  # "BUY" or "SELL"
    qty: int
    order_type: str  # "MARKET", "LIMIT", "STOP"
    status: str  # "PENDING", "ACCEPTED", "FILLED", "PARTIAL", "CANCELLED", "REJECTED"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Fill:
    """Trade execution (fill)."""

    id: str
    order_id: str
    account_id: str
    ticker: str
    side: str  # "BUY" or "SELL"
    qty: int
    price: float
    fee: float = 0.0
    filled_at: Optional[datetime] = None


@dataclass
class Position:
    """Current position in a ticker."""

    id: Optional[str]
    account_id: str
    ticker: str
    qty: int
    avg_cost: float
    updated_at: Optional[datetime] = None


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio snapshot."""

    id: Optional[str]
    account_id: str
    equity: float
    cash: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    snapshot_at: Optional[datetime] = None

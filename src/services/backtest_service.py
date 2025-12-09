from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.services.market_data_service import MarketDataService
from src.strategies import create_strategy, get_available_strategies, BaseStrategy
from src.backtesting.engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


class BacktestService:
    """Orchestrates backtest runs by coordinating data fetching, strategy execution, and engine simulation."""

    def __init__(self, market_data: MarketDataService):
        self.market_data = market_data

    def get_available_strategies(self) -> list:
        """Return list of available strategy names."""
        return get_available_strategies()

    def run_backtest(
        self,
        ticker: str,
        strategy_name: str,
        days: int = 365,
        starting_capital: float = 10000.0,
        commission: float = 0.0,
        slippage: float = 0.0,
        strategy_params: Optional[dict] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Run a backtest for the given ticker and strategy.

        Args:
            ticker: Stock symbol
            strategy_name: Name of strategy from registry
            days: Number of trading days to look back
            starting_capital: Starting cash amount
            commission: Commission per trade in dollars
            slippage: Slippage as fraction of price
            strategy_params: Parameter overrides for strategy
            end_date: End date for backtest (defaults to today)

        Returns:
            BacktestResult with equity curve, metrics, and trades
        """
        if strategy_params is None:
            strategy_params = {}

        # Calculate date range
        if end_date is None:
            end_date = datetime.now()
        start_date = end_date - timedelta(days=int(days * 1.5))  # Fetch extra for indicator warmup

        # Fetch historical data
        logger.info(f"Fetching {ticker} data from {start_date.date()} to {end_date.date()}")
        df = self._fetch_historical_data(ticker, start_date, end_date)

        if df.empty:
            raise ValueError(f"No data returned for {ticker}")

        # Create and run strategy
        strategy = create_strategy(strategy_name, **strategy_params)
        df = strategy.run(df)

        # Trim to requested day count (after indicator warmup)
        if len(df) > days:
            df = df.iloc[-days:]

        # Run backtest engine
        engine = BacktestEngine(
            starting_capital=starting_capital,
            commission=commission,
            slippage=slippage,
        )

        result = engine.run(
            df,
            ticker=ticker,
            strategy_name=strategy_name,
            parameters=strategy_params,
        )

        return result

    def _fetch_historical_data(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data and convert to DataFrame."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        raw = self.market_data.get_daily_aggs_range(ticker, start_str, end_str)
        results = raw.get("results", [])

        if not results:
            return pd.DataFrame()

        # Convert to DataFrame
        records = []
        for r in results:
            records.append({
                "Date": pd.to_datetime(r["t"], unit="ms"),
                "Open": r["o"],
                "High": r["h"],
                "Low": r["l"],
                "Close": r["c"],
                "Volume": r["v"],
            })

        df = pd.DataFrame(records)
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)

        return df

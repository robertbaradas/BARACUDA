from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from src.services.market_data_service import MarketDataService
from src.strategies import create_strategy, get_available_strategies, BaseStrategy
from src.strategies.ensemble_strategy import EnsembleStrategy, VotingMode
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
        actual_days = len(df)
        if len(df) > days:
            df = df.iloc[-days:]
            actual_days = len(df)

        # Check for limited data availability
        if actual_days < days * 0.9:
            logger.warning(
                f"Requested {days} days but only {actual_days} days available for {ticker}. "
                f"Stock may have IPO'd recently or data may be limited."
            )

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

        # Add data availability info
        result.days_requested = days
        result.days_available = actual_days

        return result

    def run_ensemble_backtest(
        self,
        ticker: str,
        strategy_configs: List[Dict],
        voting_mode: VotingMode = VotingMode.MAJORITY,
        threshold: float = 0.5,
        days: int = 365,
        starting_capital: float = 10000.0,
        commission: float = 0.0,
        slippage: float = 0.0,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Run an ensemble backtest combining multiple strategies.

        Args:
            ticker: Stock symbol
            strategy_configs: List of dicts with 'name', 'params', and 'weight' keys
            voting_mode: How to combine signals
            threshold: Voting threshold
            days: Number of days to test
            starting_capital: Starting cash
            commission: Commission per trade
            slippage: Slippage fraction
            end_date: End date for backtest

        Returns:
            BacktestResult
        """
        # Calculate date range
        if end_date is None:
            end_date = datetime.now()
        start_date = end_date - timedelta(days=int(days * 1.5))

        # Fetch historical data
        logger.info(f"Fetching {ticker} data for ensemble backtest")
        df = self._fetch_historical_data(ticker, start_date, end_date)

        if df.empty:
            raise ValueError(f"No data returned for {ticker}")

        # Create strategy instances
        strategies = []
        weights = []
        for config in strategy_configs:
            strategy = create_strategy(config["name"], **config.get("params", {}))
            strategies.append(strategy)
            weights.append(config.get("weight", 1.0))

        # Create and run ensemble
        ensemble = EnsembleStrategy(
            strategies=strategies,
            weights=weights,
            voting_mode=voting_mode,
            threshold=threshold,
        )
        df = ensemble.run(df)

        # Trim to requested day count
        actual_days = len(df)
        if len(df) > days:
            df = df.iloc[-days:]
            actual_days = len(df)

        # Check for limited data availability
        if actual_days < days * 0.9:
            logger.warning(
                f"Requested {days} days but only {actual_days} days available for {ticker}. "
                f"Stock may have IPO'd recently or data may be limited."
            )

        # Run backtest engine
        engine = BacktestEngine(
            starting_capital=starting_capital,
            commission=commission,
            slippage=slippage,
        )

        # Build parameter summary
        params_summary = {
            "voting_mode": voting_mode.value,
            "threshold": threshold,
            "strategies": [
                {"name": c["name"], "weight": c.get("weight", 1.0), "params": c.get("params", {})}
                for c in strategy_configs
            ],
        }

        result = engine.run(
            df,
            ticker=ticker,
            strategy_name=ensemble.name,
            parameters=params_summary,
        )

        # Add data availability info
        result.days_requested = days
        result.days_available = actual_days

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

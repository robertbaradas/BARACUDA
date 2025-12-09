from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import Position


logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Record of a single trade execution."""
    date: datetime
    action: str  # "BUY", "SELL", "SHORT", "COVER"
    shares: float
    price: float
    commission: float
    equity_after: float


@dataclass
class OpenPosition:
    """Tracks an open position at backtest end."""
    direction: str  # "LONG" or "SHORT"
    shares: float
    entry_price: float
    entry_date: datetime
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    @property
    def is_winning(self) -> bool:
        """Whether the open position is currently profitable."""
        return self.unrealized_pnl > 0


@dataclass
class BacktestResult:
    """Complete results from a backtest run."""
    # Curves
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    drawdown_curve: pd.Series

    # Metrics
    total_return: float
    benchmark_return: float
    excess_return: float
    sharpe_ratio: float
    max_drawdown: float
    volatility: float

    # Trade stats
    num_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # Trade list
    trades: List[Trade] = field(default_factory=list)

    # Open position tracking
    open_position: Optional[OpenPosition] = None
    adjusted_win_rate: Optional[float] = None  # Win rate if open position were closed

    # Metadata
    ticker: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    starting_capital: float = 10000.0
    strategy_name: str = ""
    parameters: dict = field(default_factory=dict)

    @property
    def has_open_position(self) -> bool:
        """Whether there is an unclosed position at backtest end."""
        return self.open_position is not None


class BacktestEngine:
    """Simulates trading based on strategy signals."""

    TRADING_DAYS_PER_YEAR = 252

    def __init__(
        self,
        starting_capital: float = 10000.0,
        commission: float = 0.0,
        slippage: float = 0.0,
    ):
        """Initialize the backtest engine.

        Args:
            starting_capital: Initial cash amount
            commission: Fixed commission per trade in dollars
            slippage: Slippage as fraction of price (0.001 = 0.1%)
        """
        self.starting_capital = starting_capital
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        df: pd.DataFrame,
        signal_column: str = "signal",
        ticker: str = "",
        strategy_name: str = "",
        parameters: dict = None,
    ) -> BacktestResult:
        """Run backtest simulation.

        Args:
            df: DataFrame with OHLCV data and signal column
            signal_column: Name of column containing Position signals
            ticker: Ticker symbol for metadata
            strategy_name: Strategy name for metadata
            parameters: Strategy parameters for metadata

        Returns:
            BacktestResult with equity curve, metrics, and trade list
        """
        if parameters is None:
            parameters = {}

        df = df.copy()

        # Ensure we have required columns
        required = ["Open", "Close", signal_column]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Initialize tracking variables
        cash = self.starting_capital
        shares = 0.0
        position = Position.FLAT

        equity_history = []
        trades: List[Trade] = []

        # Iterate through each day
        for i, (idx, row) in enumerate(df.iterrows()):
            signal = Position(int(row[signal_column]))
            open_price = row["Open"]
            close_price = row["Close"]

            # Execute trades at open based on previous day's signal
            if signal != position:
                # Close existing position first
                if position == Position.LONG and shares > 0:
                    # Sell shares
                    sell_price = open_price * (1 - self.slippage)
                    proceeds = shares * sell_price - self.commission
                    cash += proceeds
                    trades.append(Trade(
                        date=idx,
                        action="SELL",
                        shares=shares,
                        price=sell_price,
                        commission=self.commission,
                        equity_after=cash,
                    ))
                    shares = 0.0

                elif position == Position.SHORT and shares < 0:
                    # Cover short
                    cover_price = open_price * (1 + self.slippage)
                    cost = abs(shares) * cover_price + self.commission
                    cash -= cost
                    trades.append(Trade(
                        date=idx,
                        action="COVER",
                        shares=abs(shares),
                        price=cover_price,
                        commission=self.commission,
                        equity_after=cash,
                    ))
                    shares = 0.0

                # Open new position
                if signal == Position.LONG:
                    # Buy shares with all available cash
                    buy_price = open_price * (1 + self.slippage)
                    shares_to_buy = (cash - self.commission) / buy_price
                    if shares_to_buy > 0:
                        cost = shares_to_buy * buy_price + self.commission
                        cash -= cost
                        shares = shares_to_buy
                        trades.append(Trade(
                            date=idx,
                            action="BUY",
                            shares=shares_to_buy,
                            price=buy_price,
                            commission=self.commission,
                            equity_after=cash + shares * close_price,
                        ))

                elif signal == Position.SHORT:
                    # Short sell with all available cash as margin
                    short_price = open_price * (1 - self.slippage)
                    shares_to_short = (cash - self.commission) / short_price
                    if shares_to_short > 0:
                        proceeds = shares_to_short * short_price - self.commission
                        cash += proceeds
                        shares = -shares_to_short
                        trades.append(Trade(
                            date=idx,
                            action="SHORT",
                            shares=shares_to_short,
                            price=short_price,
                            commission=self.commission,
                            equity_after=cash + shares * close_price,
                        ))

                position = signal

            # Calculate end-of-day equity
            if shares > 0:
                equity = cash + shares * close_price
            elif shares < 0:
                # Short position: we owe shares at current price
                equity = cash + shares * close_price
            else:
                equity = cash

            equity_history.append({"date": idx, "equity": equity})

        # Build equity curve
        equity_df = pd.DataFrame(equity_history).set_index("date")
        equity_curve = equity_df["equity"]

        # Calculate benchmark (buy and hold)
        first_close = df["Close"].iloc[0]
        benchmark_shares = self.starting_capital / first_close
        benchmark_curve = benchmark_shares * df["Close"]
        benchmark_curve.name = "benchmark"

        # Detect open position at end of backtest
        open_position = None
        if shares != 0 and len(trades) > 0:
            # Find the entry trade for the open position
            last_entry = None
            for trade in reversed(trades):
                if trade.action in ("BUY", "SHORT"):
                    last_entry = trade
                    break

            if last_entry is not None:
                current_price = df["Close"].iloc[-1]
                direction = "LONG" if shares > 0 else "SHORT"

                if direction == "LONG":
                    unrealized_pnl = (current_price - last_entry.price) * abs(shares)
                else:  # SHORT
                    unrealized_pnl = (last_entry.price - current_price) * abs(shares)

                unrealized_pnl_pct = (unrealized_pnl / (last_entry.price * abs(shares))) * 100

                open_position = OpenPosition(
                    direction=direction,
                    shares=abs(shares),
                    entry_price=last_entry.price,
                    entry_date=last_entry.date,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                )

        # Calculate metrics
        metrics = self._calculate_metrics(equity_curve, benchmark_curve, trades, open_position)

        return BacktestResult(
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            drawdown_curve=metrics["drawdown_curve"],
            total_return=metrics["total_return"],
            benchmark_return=metrics["benchmark_return"],
            excess_return=metrics["excess_return"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            volatility=metrics["volatility"],
            num_trades=len(trades),
            win_rate=metrics["win_rate"],
            avg_win=metrics["avg_win"],
            avg_loss=metrics["avg_loss"],
            profit_factor=metrics["profit_factor"],
            trades=trades,
            open_position=open_position,
            adjusted_win_rate=metrics["adjusted_win_rate"],
            ticker=ticker,
            start_date=df.index[0] if len(df) > 0 else None,
            end_date=df.index[-1] if len(df) > 0 else None,
            starting_capital=self.starting_capital,
            strategy_name=strategy_name,
            parameters=parameters,
        )

    def _calculate_metrics(
        self,
        equity_curve: pd.Series,
        benchmark_curve: pd.Series,
        trades: List[Trade],
        open_position: Optional[OpenPosition] = None,
    ) -> dict:
        """Calculate performance metrics."""

        # Returns
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100
        benchmark_return = (benchmark_curve.iloc[-1] / benchmark_curve.iloc[0] - 1) * 100
        excess_return = total_return - benchmark_return

        # Daily returns for Sharpe and volatility
        daily_returns = equity_curve.pct_change().dropna()

        # Sharpe ratio (annualized, assuming risk-free rate = 0)
        if daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(self.TRADING_DAYS_PER_YEAR)
        else:
            sharpe_ratio = 0.0

        # Volatility (annualized)
        volatility = daily_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR) * 100

        # Drawdown
        rolling_max = equity_curve.expanding().max()
        drawdown_curve = (equity_curve - rolling_max) / rolling_max * 100
        max_drawdown = drawdown_curve.min()

        # Trade statistics
        trade_pnls = []
        if len(trades) >= 2:
            # Pair up trades to calculate P&L
            for i in range(0, len(trades) - 1, 2):
                if i + 1 < len(trades):
                    entry = trades[i]
                    exit_trade = trades[i + 1]
                    if entry.action in ("BUY", "SHORT"):
                        if entry.action == "BUY":
                            pnl = (exit_trade.price - entry.price) * entry.shares
                        else:  # SHORT
                            pnl = (entry.price - exit_trade.price) * entry.shares
                        pnl -= entry.commission + exit_trade.commission
                        trade_pnls.append(pnl)

        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]

        win_rate = len(wins) / len(trade_pnls) * 100 if trade_pnls else 0.0
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Calculate adjusted win rate (including open position as if closed)
        adjusted_win_rate = None
        if open_position is not None:
            # Create a hypothetical trade list including the open position
            adjusted_pnls = trade_pnls.copy()
            adjusted_pnls.append(open_position.unrealized_pnl)

            adjusted_wins = [p for p in adjusted_pnls if p > 0]
            adjusted_win_rate = len(adjusted_wins) / len(adjusted_pnls) * 100 if adjusted_pnls else 0.0

        return {
            "total_return": total_return,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "volatility": volatility,
            "drawdown_curve": drawdown_curve,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "adjusted_win_rate": adjusted_win_rate,
        }

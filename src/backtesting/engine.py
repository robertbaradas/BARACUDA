from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import Position


logger = logging.getLogger(__name__)


class TerminationReason(Enum):
    """Reasons why a backtest may terminate early."""
    NONE = "none"
    MARGIN_CALL = "margin_call"
    BANKRUPTCY = "bankruptcy"


@dataclass
class Trade:
    """Record of a single trade execution."""
    date: datetime
    action: str  # "BUY", "SELL", "SHORT", "COVER", "FORCED_COVER", "FORCED_SELL"
    shares: float
    price: float
    commission: float
    equity_after: float
    is_forced: bool = False  # True if this was a forced liquidation


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

    # Termination tracking
    terminated_early: bool = False
    termination_reason: TerminationReason = TerminationReason.NONE
    termination_date: Optional[datetime] = None
    termination_equity: Optional[float] = None
    termination_details: str = ""

    # Metadata
    ticker: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    starting_capital: float = 10000.0
    strategy_name: str = ""
    parameters: dict = field(default_factory=dict)

    # Configuration used
    margin_requirement: float = 0.5
    margin_call_threshold: float = 0.25

    # Data availability
    days_requested: int = 0
    days_available: int = 0

    @property
    def has_open_position(self) -> bool:
        """Whether there is an unclosed position at backtest end."""
        return self.open_position is not None

    @property
    def data_limited(self) -> bool:
        """Check if we got significantly less data than requested."""
        if self.days_requested == 0:
            return False
        return self.days_available < self.days_requested * 0.9

    @property
    def data_coverage_pct(self) -> float:
        """Return percentage of requested data that was available."""
        if self.days_requested == 0:
            return 100.0
        return (self.days_available / self.days_requested) * 100

    @property
    def was_margin_called(self) -> bool:
        """Check if backtest was terminated due to margin call."""
        return self.termination_reason == TerminationReason.MARGIN_CALL

    @property
    def went_bankrupt(self) -> bool:
        """Check if backtest was terminated due to bankruptcy."""
        return self.termination_reason == TerminationReason.BANKRUPTCY


class BacktestEngine:
    """Simulates trading based on strategy signals with margin and bankruptcy protection."""

    TRADING_DAYS_PER_YEAR = 252

    def __init__(
        self,
        starting_capital: float = 10000.0,
        commission: float = 0.0,
        slippage: float = 0.0,
        margin_requirement: float = 0.5,  # Reg T: 50%
        margin_call_threshold: float = 0.25,  # 25% of starting capital
        enable_margin_protection: bool = True,
    ):
        """Initialize the backtest engine.

        Args:
            starting_capital: Initial cash amount
            commission: Fixed commission per trade in dollars
            slippage: Slippage as fraction of price (0.001 = 0.1%)
            margin_requirement: Minimum margin required for short positions (0.5 = 50%)
            margin_call_threshold: Equity threshold as fraction of starting capital (0.25 = 25%)
            enable_margin_protection: Whether to enforce margin calls and bankruptcy protection
        """
        self.starting_capital = starting_capital
        self.commission = commission
        self.slippage = slippage
        self.margin_requirement = margin_requirement
        self.margin_call_threshold = margin_call_threshold
        self.enable_margin_protection = enable_margin_protection

        # Calculated thresholds
        self.margin_call_level = starting_capital * margin_call_threshold

    def run(
        self,
        df: pd.DataFrame,
        signal_column: str = "signal",
        ticker: str = "",
        strategy_name: str = "",
        parameters: dict = None,
    ) -> BacktestResult:
        """Run backtest simulation with margin and bankruptcy protection.

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
        entry_date = None
        entry_price = None

        equity_history = []
        trades: List[Trade] = []

        # Termination tracking
        terminated_early = False
        termination_reason = TerminationReason.NONE
        termination_date = None
        termination_equity = None
        termination_details = ""

        # Iterate through each day
        for i, (idx, row) in enumerate(df.iterrows()):
            # Check if we've already terminated
            if terminated_early:
                # Continue recording equity (flatline) for the chart
                equity_history.append({"date": idx, "equity": termination_equity})
                continue

            signal = Position(int(row[signal_column]))
            open_price = row["Open"]
            close_price = row["Close"]

            # Calculate current equity before any trades
            if shares > 0:
                current_equity = cash + shares * open_price
            elif shares < 0:
                current_equity = cash + shares * open_price  # shares is negative
            else:
                current_equity = cash

            # Check for bankruptcy (equity <= 0)
            if self.enable_margin_protection and current_equity <= 0:
                terminated_early = True
                termination_reason = TerminationReason.BANKRUPTCY
                termination_date = idx
                termination_equity = max(0, current_equity)
                termination_details = (
                    f"Account went bankrupt. Equity dropped to ${current_equity:,.2f}. "
                    f"All trading ceased."
                )
                logger.warning(f"BANKRUPTCY on {idx}: Equity = ${current_equity:,.2f}")
                equity_history.append({"date": idx, "equity": termination_equity})
                continue

            # Check for margin call (equity below threshold)
            if self.enable_margin_protection and current_equity < self.margin_call_level:
                # Force liquidate any open position
                if shares != 0:
                    if shares > 0:
                        # Force sell long position
                        sell_price = open_price * (1 - self.slippage)
                        proceeds = shares * sell_price - self.commission
                        cash += proceeds
                        trades.append(Trade(
                            date=idx,
                            action="FORCED_SELL",
                            shares=shares,
                            price=sell_price,
                            commission=self.commission,
                            equity_after=cash,
                            is_forced=True,
                        ))
                        logger.warning(f"MARGIN CALL on {idx}: Forced SELL {shares:.2f} shares @ ${sell_price:.2f}")
                        shares = 0.0
                    else:
                        # Force cover short position
                        cover_price = open_price * (1 + self.slippage)
                        cost = abs(shares) * cover_price + self.commission
                        cash -= cost
                        trades.append(Trade(
                            date=idx,
                            action="FORCED_COVER",
                            shares=abs(shares),
                            price=cover_price,
                            commission=self.commission,
                            equity_after=cash,
                            is_forced=True,
                        ))
                        logger.warning(f"MARGIN CALL on {idx}: Forced COVER {abs(shares):.2f} shares @ ${cover_price:.2f}")
                        shares = 0.0

                terminated_early = True
                termination_reason = TerminationReason.MARGIN_CALL
                termination_date = idx
                termination_equity = cash
                termination_details = (
                    f"Margin call triggered. Equity (${current_equity:,.2f}) fell below "
                    f"{self.margin_call_threshold:.0%} maintenance threshold (${self.margin_call_level:,.2f}). "
                    f"All positions were force-liquidated. Final equity: ${cash:,.2f}"
                )
                equity_history.append({"date": idx, "equity": cash})
                position = Position.FLAT
                entry_date = None
                entry_price = None
                continue

            # Execute trades at open based on signal
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
                    entry_date = None
                    entry_price = None

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
                    entry_date = None
                    entry_price = None

                # Open new position
                if signal == Position.LONG:
                    # Buy shares with all available cash
                    buy_price = open_price * (1 + self.slippage)
                    shares_to_buy = (cash - self.commission) / buy_price
                    if shares_to_buy > 0:
                        cost = shares_to_buy * buy_price + self.commission
                        cash -= cost
                        shares = shares_to_buy
                        entry_date = idx
                        entry_price = buy_price
                        trades.append(Trade(
                            date=idx,
                            action="BUY",
                            shares=shares_to_buy,
                            price=buy_price,
                            commission=self.commission,
                            equity_after=cash + shares * close_price,
                        ))

                elif signal == Position.SHORT:
                    # Short sell with margin requirement
                    short_price = open_price * (1 - self.slippage)

                    # Apply margin requirement for shorts
                    if self.enable_margin_protection:
                        # With 50% margin, you can short up to 2x your cash
                        max_short_value = cash / self.margin_requirement
                        shares_to_short = min(
                            (cash - self.commission) / short_price,  # Original calculation
                            max_short_value / short_price  # Margin-limited
                        )
                    else:
                        shares_to_short = (cash - self.commission) / short_price

                    if shares_to_short > 0:
                        proceeds = shares_to_short * short_price - self.commission
                        cash += proceeds
                        shares = -shares_to_short
                        entry_date = idx
                        entry_price = short_price
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

        # Detect open position at end of backtest (only if not terminated)
        open_position = None
        if not terminated_early and shares != 0 and entry_date is not None and entry_price is not None:
            current_price = df["Close"].iloc[-1]
            direction = "LONG" if shares > 0 else "SHORT"

            if direction == "LONG":
                unrealized_pnl = (current_price - entry_price) * abs(shares)
            else:  # SHORT
                unrealized_pnl = (entry_price - current_price) * abs(shares)

            unrealized_pnl_pct = (unrealized_pnl / (entry_price * abs(shares))) * 100

            open_position = OpenPosition(
                direction=direction,
                shares=abs(shares),
                entry_price=entry_price,
                entry_date=entry_date,
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
            terminated_early=terminated_early,
            termination_reason=termination_reason,
            termination_date=termination_date,
            termination_equity=termination_equity,
            termination_details=termination_details,
            ticker=ticker,
            start_date=df.index[0] if len(df) > 0 else None,
            end_date=df.index[-1] if len(df) > 0 else None,
            starting_capital=self.starting_capital,
            strategy_name=strategy_name,
            parameters=parameters,
            margin_requirement=self.margin_requirement,
            margin_call_threshold=self.margin_call_threshold,
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

        # Filter out zero returns from flatline (terminated) periods for accurate metrics
        active_returns = daily_returns[daily_returns != 0]

        # Sharpe ratio (annualized, assuming risk-free rate = 0)
        if len(active_returns) > 0 and active_returns.std() > 0:
            sharpe_ratio = (active_returns.mean() / active_returns.std()) * np.sqrt(self.TRADING_DAYS_PER_YEAR)
        else:
            sharpe_ratio = 0.0

        # Volatility (annualized)
        if len(active_returns) > 0:
            volatility = active_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR) * 100
        else:
            volatility = 0.0

        # Drawdown
        rolling_max = equity_curve.expanding().max()
        drawdown_curve = (equity_curve - rolling_max) / rolling_max * 100
        max_drawdown = drawdown_curve.min()

        # Trade statistics (excluding forced trades for win rate calculation)
        trade_pnls = self._calculate_closed_trade_pnls(trades)

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

    def _calculate_closed_trade_pnls(self, trades: List[Trade]) -> List[float]:
        """Calculate P&L for each completed round-trip trade."""
        trade_pnls = []

        i = 0
        while i < len(trades) - 1:
            entry = trades[i]
            exit_trade = trades[i + 1]

            # Check if this is a valid entry/exit pair
            if entry.action == "BUY" and exit_trade.action in ("SELL", "FORCED_SELL"):
                pnl = (exit_trade.price - entry.price) * entry.shares
                pnl -= entry.commission + exit_trade.commission
                trade_pnls.append(pnl)
                i += 2
            elif entry.action == "SHORT" and exit_trade.action in ("COVER", "FORCED_COVER"):
                pnl = (entry.price - exit_trade.price) * entry.shares
                pnl -= entry.commission + exit_trade.commission
                trade_pnls.append(pnl)
                i += 2
            else:
                i += 1

        return trade_pnls

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from src.strategies.base_strategy import (
    BaseStrategy,
    ChartConfig,
    Position,
    StrategyParameter,
)


class MACDStrategy(BaseStrategy):
    """Moving Average Convergence Divergence strategy."""

    @property
    def name(self) -> str:
        return "MACD"

    @property
    def display_name(self) -> str:
        return "MACD (Moving Average Convergence Divergence)"

    @property
    def description(self) -> str:
        return (
            "MACD measures momentum by comparing two exponential moving averages. "
            "The MACD line crossing above the signal line suggests bullish momentum; "
            "crossing below suggests bearish momentum. The histogram shows the difference "
            "between the MACD and signal lines."
        )

    def get_parameters(self) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="fast_period",
                label="Fast EMA Period",
                param_type="int",
                default=12,
                min_value=2,
                max_value=100,
                description="Period for the fast exponential moving average",
            ),
            StrategyParameter(
                name="slow_period",
                label="Slow EMA Period",
                param_type="int",
                default=26,
                min_value=2,
                max_value=200,
                description="Period for the slow exponential moving average",
            ),
            StrategyParameter(
                name="signal_period",
                label="Signal Line Period",
                param_type="int",
                default=9,
                min_value=2,
                max_value=50,
                description="Period for the signal line EMA",
            ),
            StrategyParameter(
                name="signal_mode",
                label="Signal Mode",
                param_type="choice",
                default="histogram",
                choices=["histogram", "crossover"],
                description="'histogram' uses histogram sign; 'crossover' uses MACD/signal crossovers",
            ),
        ]

    def calculate_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate MACD, Signal line, and Histogram."""
        fast = self.get_param("fast_period")
        slow = self.get_param("slow_period")
        signal = self.get_param("signal_period")

        close = df["Close"]

        # Calculate EMAs
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        # MACD line = Fast EMA - Slow EMA
        df["MACD"] = ema_fast - ema_slow

        # Signal line = EMA of MACD
        df["MACD_signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()

        # Histogram = MACD - Signal
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MACD."""
        signal_mode = self.get_param("signal_mode")
        signals = pd.Series(Position.FLAT, index=df.index)

        if signal_mode == "histogram":
            # Positive histogram = LONG, negative = SHORT
            signals[df["MACD_hist"] > 0] = Position.LONG
            signals[df["MACD_hist"] < 0] = Position.SHORT

        elif signal_mode == "crossover":
            # Detect crossovers
            macd = df["MACD"]
            signal_line = df["MACD_signal"]

            # MACD crosses above signal = LONG
            # MACD crosses below signal = SHORT
            cross_above = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))
            cross_below = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))

            # Forward-fill the position after crossover
            position = pd.Series(np.nan, index=df.index)
            position[cross_above] = Position.LONG
            position[cross_below] = Position.SHORT
            signals = position.ffill().fillna(Position.FLAT).astype(int)

        return signals

    def get_chart_config(self) -> ChartConfig:
        """MACD displays in its own subplot with histogram bars."""
        return ChartConfig(
            subplot=True,
            y_range=None,  # Auto-scale
            lines=[
                {"column": "MACD", "color": "#2196f3", "width": 1.5, "label": "MACD"},
                {"column": "MACD_signal", "color": "#ff9800", "width": 1.5, "label": "Signal"},
            ],
            bars=[
                {"column": "MACD_hist", "color_pos": "#66bb6a", "color_neg": "#ef5350", "label": "Histogram"},
            ],
            hlines=[
                {"y": 0, "color": "#888888", "style": "solid", "label": "Zero"},
            ],
        )

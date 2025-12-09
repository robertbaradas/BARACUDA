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


class MACrossoverStrategy(BaseStrategy):
    """Moving Average Crossover trend-following strategy."""

    @property
    def name(self) -> str:
        return "MA_Cross"

    @property
    def display_name(self) -> str:
        return "Moving Average Crossover"

    @property
    def description(self) -> str:
        return (
            "MA Crossover identifies trend changes by comparing two moving averages. "
            "When the fast MA crosses above the slow MA, it signals bullish momentum (buy); "
            "when it crosses below, it signals bearish momentum (sell)."
        )

    def get_parameters(self) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="fast_period",
                label="Fast MA Period",
                param_type="int",
                default=10,
                min_value=2,
                max_value=100,
                description="Period for the fast moving average",
            ),
            StrategyParameter(
                name="slow_period",
                label="Slow MA Period",
                param_type="int",
                default=30,
                min_value=5,
                max_value=300,
                description="Period for the slow moving average",
            ),
            StrategyParameter(
                name="ma_type",
                label="MA Type",
                param_type="choice",
                default="EMA",
                choices=["SMA", "EMA"],
                description="Type of moving average: Simple (SMA) or Exponential (EMA)",
            ),
            StrategyParameter(
                name="signal_mode",
                label="Signal Mode",
                param_type="choice",
                default="crossover",
                choices=["crossover", "position"],
                description="'crossover' trades only on crosses; 'position' holds based on MA relationship",
            ),
        ]

    def calculate_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate fast and slow moving averages."""
        fast_period = self.get_param("fast_period")
        slow_period = self.get_param("slow_period")
        ma_type = self.get_param("ma_type")

        close = df["Close"]

        if ma_type == "SMA":
            df["MA_fast"] = close.rolling(window=fast_period).mean()
            df["MA_slow"] = close.rolling(window=slow_period).mean()
        else:  # EMA
            df["MA_fast"] = close.ewm(span=fast_period, adjust=False).mean()
            df["MA_slow"] = close.ewm(span=slow_period, adjust=False).mean()

        # Difference for analysis
        df["MA_diff"] = df["MA_fast"] - df["MA_slow"]

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MA crossover."""
        signal_mode = self.get_param("signal_mode")
        signals = pd.Series(Position.FLAT, index=df.index)

        fast = df["MA_fast"]
        slow = df["MA_slow"]

        if signal_mode == "position":
            # Simple position: fast > slow = LONG, fast < slow = SHORT
            signals[fast > slow] = Position.LONG
            signals[fast < slow] = Position.SHORT

        elif signal_mode == "crossover":
            # Only trade on crossovers
            prev_fast = fast.shift(1)
            prev_slow = slow.shift(1)

            # Golden cross: fast crosses above slow
            golden_cross = (fast > slow) & (prev_fast <= prev_slow)
            # Death cross: fast crosses below slow
            death_cross = (fast < slow) & (prev_fast >= prev_slow)

            position = pd.Series(np.nan, index=df.index)
            position[golden_cross] = Position.LONG
            position[death_cross] = Position.SHORT

            signals = position.ffill().fillna(Position.FLAT).astype(int)

        return signals

    def get_chart_config(self) -> ChartConfig:
        """MA lines overlay on price chart."""
        return ChartConfig(
            subplot=False,  # Overlay on price
            y_range=None,
            lines=[
                {"column": "MA_fast", "color": "#4fc3f7", "width": 1.5, "label": "Fast MA"},
                {"column": "MA_slow", "color": "#ff8a65", "width": 1.5, "label": "Slow MA"},
            ],
        )

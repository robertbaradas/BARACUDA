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


class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands mean-reversion strategy."""

    @property
    def name(self) -> str:
        return "BB"

    @property
    def display_name(self) -> str:
        return "Bollinger Bands"

    @property
    def description(self) -> str:
        return (
            "Bollinger Bands measure volatility using standard deviations around a moving average. "
            "Price touching the lower band suggests oversold conditions (buy signal); "
            "price touching the upper band suggests overbought conditions (sell signal)."
        )

    def get_parameters(self) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="period",
                label="MA Period",
                param_type="int",
                default=20,
                min_value=5,
                max_value=100,
                description="Period for the moving average (middle band)",
            ),
            StrategyParameter(
                name="std_dev",
                label="Standard Deviations",
                param_type="float",
                default=2.0,
                min_value=0.5,
                max_value=4.0,
                description="Number of standard deviations for upper/lower bands",
            ),
            StrategyParameter(
                name="signal_mode",
                label="Signal Mode",
                param_type="choice",
                default="touch",
                choices=["touch", "cross"],
                description="'touch' signals when price touches band; 'cross' signals when price crosses band",
            ),
        ]

    def calculate_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        period = self.get_param("period")
        std_dev = self.get_param("std_dev")

        close = df["Close"]

        # Middle band = Simple Moving Average
        df["BB_middle"] = close.rolling(window=period).mean()

        # Standard deviation
        rolling_std = close.rolling(window=period).std()

        # Upper and lower bands
        df["BB_upper"] = df["BB_middle"] + (rolling_std * std_dev)
        df["BB_lower"] = df["BB_middle"] - (rolling_std * std_dev)

        # Percent B: where price is relative to bands (0 = lower, 1 = upper)
        df["BB_pctB"] = (close - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"])

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on Bollinger Bands."""
        signal_mode = self.get_param("signal_mode")
        signals = pd.Series(Position.FLAT, index=df.index)

        close = df["Close"]
        upper = df["BB_upper"]
        lower = df["BB_lower"]

        if signal_mode == "touch":
            # Price at or below lower band = LONG (oversold)
            # Price at or above upper band = SHORT (overbought)
            signals[close <= lower] = Position.LONG
            signals[close >= upper] = Position.SHORT

            # Forward-fill positions in the middle
            mask_middle = (close > lower) & (close < upper)
            signals[mask_middle] = np.nan
            signals = signals.ffill().fillna(Position.FLAT).astype(int)

        elif signal_mode == "cross":
            # Cross below lower band = LONG
            # Cross above upper band = SHORT
            prev_close = close.shift(1)

            cross_below_lower = (close <= lower) & (prev_close > lower.shift(1))
            cross_above_upper = (close >= upper) & (prev_close < upper.shift(1))

            position = pd.Series(np.nan, index=df.index)
            position[cross_below_lower] = Position.LONG
            position[cross_above_upper] = Position.SHORT

            # Also exit when crossing back to middle
            cross_to_middle_from_below = (close > lower) & (prev_close <= lower.shift(1))
            cross_to_middle_from_above = (close < upper) & (prev_close >= upper.shift(1))
            position[cross_to_middle_from_below | cross_to_middle_from_above] = Position.FLAT

            signals = position.ffill().fillna(Position.FLAT).astype(int)

        return signals

    def get_chart_config(self) -> ChartConfig:
        """Bollinger Bands overlay on price chart (no separate subplot)."""
        return ChartConfig(
            subplot=False,  # Overlay on price
            y_range=None,
            lines=[
                {"column": "BB_upper", "color": "#ef5350", "width": 1, "label": "Upper Band"},
                {"column": "BB_middle", "color": "#ffa726", "width": 1, "label": "Middle Band"},
                {"column": "BB_lower", "color": "#66bb6a", "width": 1, "label": "Lower Band"},
            ],
        )

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


class RSIStrategy(BaseStrategy):
    """Relative Strength Index momentum strategy."""

    @property
    def name(self) -> str:
        return "RSI"

    @property
    def display_name(self) -> str:
        return "Relative Strength Index"

    @property
    def description(self) -> str:
        return (
            "RSI measures momentum by comparing average gains to average losses over a period. "
            "Values below the oversold threshold suggest buying opportunity; "
            "values above the overbought threshold suggest selling opportunity."
        )

    def get_parameters(self) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="period",
                label="RSI Period",
                param_type="int",
                default=14,
                min_value=2,
                max_value=100,
                description="Number of periods for RSI calculation",
            ),
            StrategyParameter(
                name="oversold",
                label="Oversold Threshold",
                param_type="int",
                default=30,
                min_value=0,
                max_value=50,
                description="RSI below this level generates a buy signal",
            ),
            StrategyParameter(
                name="overbought",
                label="Overbought Threshold",
                param_type="int",
                default=70,
                min_value=50,
                max_value=100,
                description="RSI above this level generates a sell signal",
            ),
            StrategyParameter(
                name="middle_behavior",
                label="Middle Zone Behavior",
                param_type="choice",
                default="hold",
                choices=["hold", "flat"],
                description="'hold' keeps previous position; 'flat' exits to cash",
            ),
        ]

    def calculate_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate RSI and add to DataFrame."""
        period = self.get_param("period")
        close = df["Close"]

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        df["RSI"] = rsi
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on RSI thresholds."""
        oversold = self.get_param("oversold")
        overbought = self.get_param("overbought")
        middle_behavior = self.get_param("middle_behavior")

        rsi = df["RSI"]
        signals = pd.Series(Position.FLAT, index=df.index)

        # Below oversold = LONG, above overbought = SHORT
        signals[rsi < oversold] = Position.LONG
        signals[rsi > overbought] = Position.SHORT

        # Handle middle zone
        if middle_behavior == "hold":
            # Forward-fill the last non-middle signal
            mask_middle = (rsi >= oversold) & (rsi <= overbought)
            signals[mask_middle] = np.nan
            signals = signals.ffill().fillna(Position.FLAT).astype(int)

        return signals

    def get_chart_config(self) -> ChartConfig:
        """RSI displays in its own subplot with 0-100 range."""
        oversold = self.get_param("oversold")
        overbought = self.get_param("overbought")

        return ChartConfig(
            subplot=True,
            y_range=(0, 100),
            lines=[{"column": "RSI", "color": "#FFD700", "width": 1.5}],
            hlines=[
                {"y": oversold, "color": "#00FF00", "style": "dashed", "label": f"Oversold ({oversold})"},
                {"y": overbought, "color": "#FF4444", "style": "dashed", "label": f"Overbought ({overbought})"},
                {"y": 50, "color": "#888888", "style": "dotted", "label": "Midline"},
            ],
        )

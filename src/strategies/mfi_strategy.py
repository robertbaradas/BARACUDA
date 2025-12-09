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


class MFIStrategy(BaseStrategy):
    """Money Flow Index strategy - RSI weighted by volume."""

    @property
    def name(self) -> str:
        return "MFI"

    @property
    def display_name(self) -> str:
        return "Money Flow Index"

    @property
    def description(self) -> str:
        return (
            "MFI is a volume-weighted RSI that measures buying and selling pressure. "
            "Values below the oversold threshold suggest accumulation (buy signal); "
            "values above the overbought threshold suggest distribution (sell signal)."
        )

    def get_parameters(self) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="period",
                label="MFI Period",
                param_type="int",
                default=14,
                min_value=2,
                max_value=100,
                description="Number of periods for MFI calculation",
            ),
            StrategyParameter(
                name="oversold",
                label="Oversold Threshold",
                param_type="int",
                default=20,
                min_value=0,
                max_value=50,
                description="MFI below this level generates a buy signal",
            ),
            StrategyParameter(
                name="overbought",
                label="Overbought Threshold",
                param_type="int",
                default=80,
                min_value=50,
                max_value=100,
                description="MFI above this level generates a sell signal",
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
        """Calculate Money Flow Index."""
        period = self.get_param("period")

        # Typical Price
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3

        # Raw Money Flow
        raw_money_flow = typical_price * df["Volume"]

        # Money Flow Direction
        tp_diff = typical_price.diff()

        # Positive and Negative Money Flow
        positive_flow = raw_money_flow.where(tp_diff > 0, 0)
        negative_flow = raw_money_flow.where(tp_diff < 0, 0)

        # Sum over period
        positive_mf_sum = positive_flow.rolling(window=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period).sum()

        # Money Flow Ratio
        mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)

        # Money Flow Index
        df["MFI"] = 100 - (100 / (1 + mf_ratio))

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MFI thresholds."""
        oversold = self.get_param("oversold")
        overbought = self.get_param("overbought")
        middle_behavior = self.get_param("middle_behavior")

        mfi = df["MFI"]
        signals = pd.Series(Position.FLAT, index=df.index)

        # Below oversold = LONG, above overbought = SHORT
        signals[mfi < oversold] = Position.LONG
        signals[mfi > overbought] = Position.SHORT

        # Handle middle zone
        if middle_behavior == "hold":
            mask_middle = (mfi >= oversold) & (mfi <= overbought)
            signals[mask_middle] = np.nan
            signals = signals.ffill().fillna(Position.FLAT).astype(int)

        return signals

    def get_chart_config(self) -> ChartConfig:
        """MFI displays in its own subplot with 0-100 range."""
        oversold = self.get_param("oversold")
        overbought = self.get_param("overbought")

        return ChartConfig(
            subplot=True,
            y_range=(0, 100),
            lines=[{"column": "MFI", "color": "#ce93d8", "width": 1.5}],
            hlines=[
                {"y": oversold, "color": "#66bb6a", "style": "dashed", "label": f"Oversold ({oversold})"},
                {"y": overbought, "color": "#ef5350", "style": "dashed", "label": f"Overbought ({overbought})"},
                {"y": 50, "color": "#888888", "style": "dotted", "label": "Midline"},
            ],
        )

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Literal, Optional

import pandas as pd


class Position(IntEnum):
    """Trading position signals."""
    SHORT = -1
    FLAT = 0
    LONG = 1


@dataclass
class StrategyParameter:
    """Describes a configurable strategy parameter for dynamic UI generation."""
    name: str
    label: str
    param_type: Literal["int", "float", "choice"]
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[List[Any]] = None
    description: str = ""


@dataclass
class ChartConfig:
    """Configuration for how to render the strategy's indicator on a chart."""
    subplot: bool = False  # True if indicator needs its own panel (RSI), False if overlaid (MA)
    y_range: Optional[tuple] = None  # Fixed range like (0, 100) for RSI, None for auto-scale
    lines: List[Dict[str, Any]] = field(default_factory=list)  # Line plots: [{"column": "RSI", "color": "yellow"}]
    bars: List[Dict[str, Any]] = field(default_factory=list)  # Bar plots: [{"column": "MACD_hist", "color_pos": "green", "color_neg": "red"}]
    hlines: List[Dict[str, Any]] = field(default_factory=list)  # Horizontal lines: [{"y": 70, "color": "red", "style": "dashed"}]


class BaseStrategy(ABC):
    """Abstract base class for all technical indicator strategies."""

    def __init__(self, **params):
        """Initialize strategy with parameter overrides."""
        self._params = self._build_params(params)

    def _build_params(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Build parameter dict from defaults with overrides applied."""
        params = {}
        for p in self.get_parameters():
            params[p.name] = overrides.get(p.name, p.default)
        return params

    def get_param(self, name: str) -> Any:
        """Get current value of a parameter."""
        return self._params.get(name)

    def set_param(self, name: str, value: Any) -> None:
        """Update a parameter value."""
        self._params[name] = value

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for the strategy (e.g., 'RSI')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'Relative Strength Index')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the indicator measures and how signals are generated."""
        pass

    @abstractmethod
    def get_parameters(self) -> List[StrategyParameter]:
        """Return list of configurable parameters for this strategy."""
        pass

    @abstractmethod
    def calculate_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicator values and add columns to the DataFrame.

        Args:
            df: DataFrame with columns: Open, High, Low, Close, Volume

        Returns:
            Same DataFrame with additional indicator columns
        """
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate trading signals based on indicator values.

        Args:
            df: DataFrame with indicator columns already added

        Returns:
            Series of Position values (LONG=1, SHORT=-1, FLAT=0)
        """
        pass

    @abstractmethod
    def get_chart_config(self) -> ChartConfig:
        """Return configuration for rendering this indicator on a chart."""
        pass

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run full pipeline: calculate indicators, generate signals, shift to avoid look-ahead bias.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with indicator columns and 'signal' column (shifted by 1)
        """
        df = self.calculate_indicator(df.copy())
        signals = self.generate_signals(df)
        # Shift signals by 1 to avoid look-ahead bias
        # Today's signal is acted on at tomorrow's open
        df["signal"] = signals.shift(1).fillna(Position.FLAT).astype(int)
        return df

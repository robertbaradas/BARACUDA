from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import (
    BaseStrategy,
    ChartConfig,
    Position,
    StrategyParameter,
)


class VotingMode(Enum):
    """Ensemble voting modes."""
    UNANIMOUS = "unanimous"   # All strategies must agree
    MAJORITY = "majority"     # More than half must agree
    WEIGHTED = "weighted"     # Weighted sum compared to threshold
    ANY = "any"               # Any single strategy triggers


class EnsembleStrategy:
    """Combines multiple strategies using voting mechanisms.

    Note: This is NOT a subclass of BaseStrategy because it doesn't have
    its own indicator - it aggregates signals from other strategies.
    """

    def __init__(
        self,
        strategies: List[BaseStrategy],
        weights: Optional[List[float]] = None,
        voting_mode: VotingMode = VotingMode.MAJORITY,
        threshold: float = 0.5,
    ):
        """Initialize ensemble strategy.

        Args:
            strategies: List of strategy instances to combine
            weights: Optional weights for each strategy (for weighted voting)
            voting_mode: How to aggregate signals
            threshold: Threshold for majority/weighted voting (0.0 to 1.0)
        """
        if not strategies:
            raise ValueError("Ensemble requires at least one strategy")

        self.strategies = strategies
        self.weights = weights or [1.0] * len(strategies)
        self.voting_mode = voting_mode
        self.threshold = threshold

        if len(self.weights) != len(self.strategies):
            raise ValueError("Number of weights must match number of strategies")

    @property
    def name(self) -> str:
        strategy_names = "+".join(s.name for s in self.strategies)
        return f"Ensemble({strategy_names})"

    @property
    def display_name(self) -> str:
        return f"Ensemble: {', '.join(s.name for s in self.strategies)}"

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run all strategies and combine their signals.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with individual strategy signals and combined 'signal' column
        """
        df = df.copy()

        # Run each strategy and collect signals
        signal_columns = []
        for i, strategy in enumerate(self.strategies):
            # Calculate indicator and generate signals
            df = strategy.calculate_indicator(df)
            signals = strategy.generate_signals(df)
            col_name = f"signal_{strategy.name}"
            df[col_name] = signals
            signal_columns.append(col_name)

        # Combine signals using voting mode
        df["signal"] = self._vote(df, signal_columns)

        # Shift to avoid look-ahead bias
        df["signal"] = df["signal"].shift(1).fillna(Position.FLAT).astype(int)

        return df

    def _vote(self, df: pd.DataFrame, signal_columns: List[str]) -> pd.Series:
        """Aggregate signals using the configured voting mode."""
        n = len(df)
        result = pd.Series(Position.FLAT, index=df.index)

        # Extract signal arrays
        signals = np.array([df[col].values for col in signal_columns])  # Shape: (n_strategies, n_rows)
        weights = np.array(self.weights)

        for i in range(n):
            row_signals = signals[:, i]
            result.iloc[i] = self._vote_single(row_signals, weights)

        return result

    def _vote_single(self, signals: np.ndarray, weights: np.ndarray) -> int:
        """Vote on a single row of signals."""
        n_strategies = len(signals)

        if self.voting_mode == VotingMode.UNANIMOUS:
            # All must agree
            if np.all(signals == Position.LONG):
                return Position.LONG
            elif np.all(signals == Position.SHORT):
                return Position.SHORT
            else:
                return Position.FLAT

        elif self.voting_mode == VotingMode.MAJORITY:
            # Count votes
            long_count = np.sum(signals == Position.LONG)
            short_count = np.sum(signals == Position.SHORT)
            required = n_strategies * self.threshold

            if long_count > required:
                return Position.LONG
            elif short_count > required:
                return Position.SHORT
            else:
                return Position.FLAT

        elif self.voting_mode == VotingMode.WEIGHTED:
            # Weighted sum: LONG=+1, SHORT=-1, FLAT=0
            weighted_sum = np.sum(signals * weights)
            total_weight = np.sum(weights)
            normalized = weighted_sum / total_weight if total_weight > 0 else 0

            if normalized > self.threshold:
                return Position.LONG
            elif normalized < -self.threshold:
                return Position.SHORT
            else:
                return Position.FLAT

        elif self.voting_mode == VotingMode.ANY:
            # Any long or short triggers
            if Position.LONG in signals:
                return Position.LONG
            elif Position.SHORT in signals:
                return Position.SHORT
            else:
                return Position.FLAT

        return Position.FLAT

    def get_strategy_signals(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Get individual strategy signals for analysis.

        Args:
            df: DataFrame after running ensemble

        Returns:
            Dict mapping strategy name to its signal series
        """
        result = {}
        for strategy in self.strategies:
            col = f"signal_{strategy.name}"
            if col in df.columns:
                result[strategy.name] = df[col]
        return result

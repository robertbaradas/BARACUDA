"""Unit tests for strategy classes."""

import numpy as np
import pandas as pd
import pytest

from src.strategies import create_strategy, get_available_strategies, Position
from src.strategies.rsi_strategy import RSIStrategy


class TestStrategyRegistry:
    """Tests for strategy registry functions."""

    def test_get_available_strategies(self):
        """Verify RSI is registered."""
        strategies = get_available_strategies()
        assert "RSI" in strategies

    def test_create_strategy_valid(self):
        """Create strategy by name."""
        strategy = create_strategy("RSI")
        assert isinstance(strategy, RSIStrategy)
        assert strategy.name == "RSI"

    def test_create_strategy_with_params(self):
        """Create strategy with parameter overrides."""
        strategy = create_strategy("RSI", period=21, oversold=25)
        assert strategy.get_param("period") == 21
        assert strategy.get_param("oversold") == 25
        assert strategy.get_param("overbought") == 70  # default

    def test_create_strategy_invalid(self):
        """Unknown strategy raises ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            create_strategy("INVALID")


class TestRSIStrategy:
    """Tests for RSI strategy implementation."""

    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        np.random.seed(42)
        n = 100
        close = 100 + np.cumsum(np.random.randn(n) * 2)
        return pd.DataFrame({
            "Open": close - np.random.rand(n),
            "High": close + np.random.rand(n) * 2,
            "Low": close - np.random.rand(n) * 2,
            "Close": close,
            "Volume": np.random.randint(1000, 10000, n),
        })

    def test_calculate_indicator_adds_rsi_column(self, sample_df):
        """RSI column is added to DataFrame."""
        strategy = RSIStrategy()
        result = strategy.calculate_indicator(sample_df)
        assert "RSI" in result.columns

    def test_rsi_values_in_range(self, sample_df):
        """RSI values should be between 0 and 100."""
        strategy = RSIStrategy()
        result = strategy.calculate_indicator(sample_df)
        rsi = result["RSI"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()

    def test_generate_signals_returns_positions(self, sample_df):
        """Signals are valid Position values."""
        strategy = RSIStrategy()
        df = strategy.calculate_indicator(sample_df)
        signals = strategy.generate_signals(df)
        assert signals.isin([Position.LONG, Position.SHORT, Position.FLAT]).all()

    def test_oversold_generates_long(self):
        """RSI below oversold threshold generates LONG signal."""
        strategy = RSIStrategy(oversold=30, overbought=70)
        df = pd.DataFrame({"RSI": [25, 25, 25]})
        signals = strategy.generate_signals(df)
        assert (signals == Position.LONG).all()

    def test_overbought_generates_short(self):
        """RSI above overbought threshold generates SHORT signal."""
        strategy = RSIStrategy(oversold=30, overbought=70)
        df = pd.DataFrame({"RSI": [75, 75, 75]})
        signals = strategy.generate_signals(df)
        assert (signals == Position.SHORT).all()

    def test_run_shifts_signals(self, sample_df):
        """Run method shifts signals to avoid look-ahead bias."""
        strategy = RSIStrategy()
        result = strategy.run(sample_df)
        assert "signal" in result.columns
        # First signal should be FLAT (shifted from NaN)
        assert result["signal"].iloc[0] == Position.FLAT

    def test_chart_config(self):
        """Chart config specifies subplot with correct range."""
        strategy = RSIStrategy(oversold=30, overbought=70)
        config = strategy.get_chart_config()
        assert config.subplot is True
        assert config.y_range == (0, 100)
        assert len(config.hlines) == 3  # oversold, overbought, midline

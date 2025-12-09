"""Unit tests for MACD strategy."""

import numpy as np
import pandas as pd
import pytest

from src.strategies import create_strategy, Position
from src.strategies.macd_strategy import MACDStrategy


class TestMACDStrategy:
    """Tests for MACD strategy implementation."""

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

    def test_strategy_registered(self):
        """MACD should be in registry."""
        from src.strategies import get_available_strategies
        assert "MACD" in get_available_strategies()

    def test_create_strategy(self):
        """Can create MACD strategy via factory."""
        strategy = create_strategy("MACD")
        assert isinstance(strategy, MACDStrategy)
        assert strategy.name == "MACD"

    def test_default_parameters(self):
        """Verify default parameter values."""
        strategy = MACDStrategy()
        assert strategy.get_param("fast_period") == 12
        assert strategy.get_param("slow_period") == 26
        assert strategy.get_param("signal_period") == 9
        assert strategy.get_param("signal_mode") == "histogram"

    def test_calculate_indicator_adds_columns(self, sample_df):
        """MACD, signal, and histogram columns are added."""
        strategy = MACDStrategy()
        result = strategy.calculate_indicator(sample_df)

        assert "MACD" in result.columns
        assert "MACD_signal" in result.columns
        assert "MACD_hist" in result.columns

    def test_histogram_equals_macd_minus_signal(self, sample_df):
        """Histogram should equal MACD - Signal."""
        strategy = MACDStrategy()
        result = strategy.calculate_indicator(sample_df)

        expected_hist = result["MACD"] - result["MACD_signal"]
        pd.testing.assert_series_equal(
            result["MACD_hist"],
            expected_hist,
            check_names=False,
        )

    def test_histogram_mode_signals(self, sample_df):
        """Histogram mode: positive = LONG, negative = SHORT."""
        strategy = MACDStrategy(signal_mode="histogram")
        df = strategy.calculate_indicator(sample_df)
        signals = strategy.generate_signals(df)

        # Where histogram > 0, should be LONG
        pos_hist = df["MACD_hist"] > 0
        assert (signals[pos_hist] == Position.LONG).all()

        # Where histogram < 0, should be SHORT
        neg_hist = df["MACD_hist"] < 0
        assert (signals[neg_hist] == Position.SHORT).all()

    def test_crossover_mode_signals(self, sample_df):
        """Crossover mode generates valid positions."""
        strategy = MACDStrategy(signal_mode="crossover")
        df = strategy.calculate_indicator(sample_df)
        signals = strategy.generate_signals(df)

        # All signals should be valid Position values
        assert signals.isin([Position.LONG, Position.SHORT, Position.FLAT]).all()

    def test_run_shifts_signals(self, sample_df):
        """Run method shifts signals to avoid look-ahead bias."""
        strategy = MACDStrategy()
        result = strategy.run(sample_df)

        assert "signal" in result.columns
        # First signal should be FLAT (shifted from NaN)
        assert result["signal"].iloc[0] == Position.FLAT

    def test_chart_config(self):
        """Chart config specifies subplot with lines and bars."""
        strategy = MACDStrategy()
        config = strategy.get_chart_config()

        assert config.subplot is True
        assert config.y_range is None  # Auto-scale
        assert len(config.lines) == 2  # MACD and Signal
        assert len(config.bars) == 1   # Histogram
        assert len(config.hlines) == 1  # Zero line

    def test_custom_parameters(self, sample_df):
        """Custom parameters are applied correctly."""
        strategy = MACDStrategy(fast_period=8, slow_period=21, signal_period=5)

        assert strategy.get_param("fast_period") == 8
        assert strategy.get_param("slow_period") == 21
        assert strategy.get_param("signal_period") == 5

        # Should still calculate without errors
        result = strategy.calculate_indicator(sample_df)
        assert "MACD" in result.columns

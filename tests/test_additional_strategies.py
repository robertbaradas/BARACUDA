"""Unit tests for Bollinger Bands, MFI, and MA Crossover strategies."""

import numpy as np
import pandas as pd
import pytest

from src.strategies import create_strategy, get_available_strategies, Position
from src.strategies.bollinger_strategy import BollingerBandsStrategy
from src.strategies.mfi_strategy import MFIStrategy
from src.strategies.ma_crossover_strategy import MACrossoverStrategy


class TestBollingerBandsStrategy:
    """Tests for Bollinger Bands strategy."""

    @pytest.fixture
    def sample_df(self):
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
        assert "BB" in get_available_strategies()

    def test_create_strategy(self):
        strategy = create_strategy("BB")
        assert isinstance(strategy, BollingerBandsStrategy)

    def test_default_parameters(self):
        strategy = BollingerBandsStrategy()
        assert strategy.get_param("period") == 20
        assert strategy.get_param("std_dev") == 2.0
        assert strategy.get_param("signal_mode") == "touch"

    def test_calculate_indicator_adds_columns(self, sample_df):
        strategy = BollingerBandsStrategy()
        result = strategy.calculate_indicator(sample_df)
        assert "BB_upper" in result.columns
        assert "BB_middle" in result.columns
        assert "BB_lower" in result.columns
        assert "BB_pctB" in result.columns

    def test_upper_greater_than_lower(self, sample_df):
        strategy = BollingerBandsStrategy()
        result = strategy.calculate_indicator(sample_df)
        valid = result.dropna()
        assert (valid["BB_upper"] > valid["BB_lower"]).all()

    def test_middle_is_average(self, sample_df):
        strategy = BollingerBandsStrategy(period=20)
        result = strategy.calculate_indicator(sample_df)
        expected_middle = sample_df["Close"].rolling(20).mean()
        pd.testing.assert_series_equal(
            result["BB_middle"], expected_middle, check_names=False
        )

    def test_chart_config_not_subplot(self):
        strategy = BollingerBandsStrategy()
        config = strategy.get_chart_config()
        assert config.subplot is False  # Overlay on price

    def test_chart_config_has_three_lines(self):
        strategy = BollingerBandsStrategy()
        config = strategy.get_chart_config()
        assert len(config.lines) == 3  # Upper, middle, lower

    def test_run_produces_signal_column(self, sample_df):
        strategy = BollingerBandsStrategy()
        result = strategy.run(sample_df)
        assert "signal" in result.columns


class TestMFIStrategy:
    """Tests for MFI strategy."""

    @pytest.fixture
    def sample_df(self):
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
        assert "MFI" in get_available_strategies()

    def test_create_strategy(self):
        strategy = create_strategy("MFI")
        assert isinstance(strategy, MFIStrategy)

    def test_default_parameters(self):
        strategy = MFIStrategy()
        assert strategy.get_param("period") == 14
        assert strategy.get_param("oversold") == 20
        assert strategy.get_param("overbought") == 80
        assert strategy.get_param("middle_behavior") == "hold"

    def test_calculate_indicator_adds_mfi(self, sample_df):
        strategy = MFIStrategy()
        result = strategy.calculate_indicator(sample_df)
        assert "MFI" in result.columns

    def test_mfi_in_range(self, sample_df):
        strategy = MFIStrategy()
        result = strategy.calculate_indicator(sample_df)
        mfi = result["MFI"].dropna()
        assert (mfi >= 0).all()
        assert (mfi <= 100).all()

    def test_oversold_generates_long(self):
        strategy = MFIStrategy(oversold=20, overbought=80)
        df = pd.DataFrame({"MFI": [15, 15, 15]})
        signals = strategy.generate_signals(df)
        assert (signals == Position.LONG).all()

    def test_overbought_generates_short(self):
        strategy = MFIStrategy(oversold=20, overbought=80)
        df = pd.DataFrame({"MFI": [85, 85, 85]})
        signals = strategy.generate_signals(df)
        assert (signals == Position.SHORT).all()

    def test_chart_config_is_subplot(self):
        strategy = MFIStrategy()
        config = strategy.get_chart_config()
        assert config.subplot is True  # Separate subplot

    def test_chart_config_has_range(self):
        strategy = MFIStrategy()
        config = strategy.get_chart_config()
        assert config.y_range == (0, 100)

    def test_run_produces_signal_column(self, sample_df):
        strategy = MFIStrategy()
        result = strategy.run(sample_df)
        assert "signal" in result.columns


class TestMACrossoverStrategy:
    """Tests for MA Crossover strategy."""

    @pytest.fixture
    def sample_df(self):
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
        assert "MA_Cross" in get_available_strategies()

    def test_create_strategy(self):
        strategy = create_strategy("MA_Cross")
        assert isinstance(strategy, MACrossoverStrategy)

    def test_default_parameters(self):
        strategy = MACrossoverStrategy()
        assert strategy.get_param("fast_period") == 10
        assert strategy.get_param("slow_period") == 30
        assert strategy.get_param("ma_type") == "EMA"
        assert strategy.get_param("signal_mode") == "crossover"

    def test_calculate_indicator_adds_columns(self, sample_df):
        strategy = MACrossoverStrategy()
        result = strategy.calculate_indicator(sample_df)
        assert "MA_fast" in result.columns
        assert "MA_slow" in result.columns
        assert "MA_diff" in result.columns

    def test_sma_calculation(self, sample_df):
        strategy = MACrossoverStrategy(fast_period=10, slow_period=30, ma_type="SMA")
        result = strategy.calculate_indicator(sample_df)
        expected_fast = sample_df["Close"].rolling(10).mean()
        pd.testing.assert_series_equal(
            result["MA_fast"], expected_fast, check_names=False
        )

    def test_ema_calculation(self, sample_df):
        strategy = MACrossoverStrategy(fast_period=10, slow_period=30, ma_type="EMA")
        result = strategy.calculate_indicator(sample_df)
        expected_fast = sample_df["Close"].ewm(span=10, adjust=False).mean()
        pd.testing.assert_series_equal(
            result["MA_fast"], expected_fast, check_names=False
        )

    def test_position_mode_signals(self, sample_df):
        strategy = MACrossoverStrategy(signal_mode="position")
        df = strategy.calculate_indicator(sample_df)
        signals = strategy.generate_signals(df)

        # Where fast > slow, should be LONG
        fast_above = df["MA_fast"] > df["MA_slow"]
        assert (signals[fast_above.fillna(False)] == Position.LONG).all()

    def test_chart_config_not_subplot(self):
        strategy = MACrossoverStrategy()
        config = strategy.get_chart_config()
        assert config.subplot is False  # Overlay on price

    def test_chart_config_has_two_lines(self):
        strategy = MACrossoverStrategy()
        config = strategy.get_chart_config()
        assert len(config.lines) == 2  # Fast and slow MA

    def test_run_produces_signal_column(self, sample_df):
        strategy = MACrossoverStrategy()
        result = strategy.run(sample_df)
        assert "signal" in result.columns

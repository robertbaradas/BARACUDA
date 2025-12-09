"""Unit tests for backtesting engine."""

import numpy as np
import pandas as pd
import pytest

from src.backtesting.engine import BacktestEngine, BacktestResult
from src.strategies.base_strategy import Position


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame with signal column."""
        dates = pd.date_range("2023-01-01", periods=20, freq="D")
        return pd.DataFrame({
            "Open": [100 + i for i in range(20)],
            "High": [102 + i for i in range(20)],
            "Low": [98 + i for i in range(20)],
            "Close": [101 + i for i in range(20)],
            "Volume": [1000] * 20,
            "signal": [Position.FLAT] * 20,
        }, index=dates)

    def test_always_flat_no_trades(self, sample_df):
        """All FLAT signals should produce no trades."""
        engine = BacktestEngine(starting_capital=10000)
        result = engine.run(sample_df)
        assert result.num_trades == 0
        assert result.total_return == 0.0

    def test_buy_and_hold_matches_benchmark(self, sample_df):
        """Always LONG should approximately match benchmark."""
        sample_df["signal"] = Position.LONG
        engine = BacktestEngine(starting_capital=10000, commission=0, slippage=0)
        result = engine.run(sample_df)
        # Should be very close to benchmark (small difference due to buying at open vs close)
        assert abs(result.total_return - result.benchmark_return) < 5.0

    def test_commission_reduces_returns(self, sample_df):
        """Commission should reduce total returns."""
        sample_df["signal"] = [Position.FLAT] * 5 + [Position.LONG] * 10 + [Position.FLAT] * 5

        engine_no_comm = BacktestEngine(starting_capital=10000, commission=0)
        result_no_comm = engine_no_comm.run(sample_df)

        engine_with_comm = BacktestEngine(starting_capital=10000, commission=10)
        result_with_comm = engine_with_comm.run(sample_df)

        assert result_with_comm.total_return < result_no_comm.total_return

    def test_result_contains_equity_curve(self, sample_df):
        """Result should contain equity curve Series."""
        sample_df["signal"] = Position.LONG
        engine = BacktestEngine(starting_capital=10000)
        result = engine.run(sample_df)
        assert isinstance(result.equity_curve, pd.Series)
        assert len(result.equity_curve) == len(sample_df)

    def test_result_contains_benchmark_curve(self, sample_df):
        """Result should contain benchmark curve Series."""
        engine = BacktestEngine(starting_capital=10000)
        result = engine.run(sample_df)
        assert isinstance(result.benchmark_curve, pd.Series)
        assert len(result.benchmark_curve) == len(sample_df)

    def test_drawdown_is_negative_or_zero(self, sample_df):
        """Drawdown values should be <= 0."""
        sample_df["signal"] = Position.LONG
        engine = BacktestEngine(starting_capital=10000)
        result = engine.run(sample_df)
        assert (result.drawdown_curve <= 0).all()

    def test_metadata_preserved(self, sample_df):
        """Metadata should be included in result."""
        engine = BacktestEngine(starting_capital=10000)
        result = engine.run(
            sample_df,
            ticker="AAPL",
            strategy_name="RSI",
            parameters={"period": 14},
        )
        assert result.ticker == "AAPL"
        assert result.strategy_name == "RSI"
        assert result.parameters == {"period": 14}
        assert result.starting_capital == 10000

    def test_missing_signal_column_raises(self, sample_df):
        """Missing signal column should raise ValueError."""
        del sample_df["signal"]
        engine = BacktestEngine()
        with pytest.raises(ValueError, match="Missing required column"):
            engine.run(sample_df)

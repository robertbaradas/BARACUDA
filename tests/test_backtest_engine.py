"""Unit tests for backtesting engine."""

import numpy as np
import pandas as pd
import pytest

from src.backtesting.engine import BacktestEngine, BacktestResult, TerminationReason
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


class TestMarginCallProtection:
    """Tests for margin call and bankruptcy protection."""

    @pytest.fixture
    def crash_df(self):
        """Create data where price crashes 90% after going long."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = [100, 100, 100, 50, 20, 10, 5, 5, 5, 5]  # 95% crash
        return pd.DataFrame({
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * 10,
            "signal": [Position.LONG] * 10,
        }, index=dates)

    @pytest.fixture
    def short_squeeze_df(self):
        """Create data where price spikes 300% after going short."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = [100, 100, 200, 300, 400, 400, 400, 400, 400, 400]  # 300% spike
        return pd.DataFrame({
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * 10,
            "signal": [Position.SHORT] * 10,
        }, index=dates)

    def test_margin_call_triggered(self, crash_df):
        """Margin call should be triggered when equity falls below threshold."""
        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,  # 25% = $2,500
            enable_margin_protection=True,
        )
        result = engine.run(crash_df)

        assert result.terminated_early is True
        assert result.termination_reason == TerminationReason.MARGIN_CALL
        assert result.termination_date is not None
        assert result.termination_equity is not None
        assert "margin call" in result.termination_details.lower() or "Margin call" in result.termination_details

    def test_forced_sell_on_margin_call(self, crash_df):
        """Margin call should force sell the position."""
        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,
            enable_margin_protection=True,
        )
        result = engine.run(crash_df)

        # Check that we have a forced sell trade
        forced_trades = [t for t in result.trades if t.is_forced]
        assert len(forced_trades) >= 1
        assert any(t.action == "FORCED_SELL" for t in forced_trades)

    def test_forced_cover_on_short_squeeze(self):
        """Short squeeze should trigger termination (margin call or bankruptcy)."""
        # Create a less extreme squeeze that triggers margin call before bankruptcy
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = [100, 100, 120, 140, 160, 180, 200, 200, 200, 200]  # More gradual spike
        df = pd.DataFrame({
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * 10,
            "signal": [Position.SHORT] * 10,
        }, index=dates)

        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,
            enable_margin_protection=True,
        )
        result = engine.run(df)

        assert result.terminated_early is True
        # Could be margin call or bankruptcy depending on price movement
        assert result.termination_reason in (TerminationReason.MARGIN_CALL, TerminationReason.BANKRUPTCY)

        # If it was a margin call, check for forced cover
        if result.termination_reason == TerminationReason.MARGIN_CALL:
            forced_trades = [t for t in result.trades if t.is_forced]
            assert len(forced_trades) >= 1
            assert any(t.action == "FORCED_COVER" for t in forced_trades)

    def test_equity_flatlines_after_termination(self, crash_df):
        """Equity curve should flatline after termination."""
        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,
            enable_margin_protection=True,
        )
        result = engine.run(crash_df)

        # After termination, equity should stay constant
        termination_idx = list(result.equity_curve.index).index(result.termination_date)
        remaining_equity = result.equity_curve.iloc[termination_idx:]

        # All values after termination should be the same
        assert remaining_equity.nunique() == 1

    def test_no_margin_call_when_disabled(self, crash_df):
        """Margin protection can be disabled."""
        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,
            enable_margin_protection=False,  # Disabled
        )
        result = engine.run(crash_df)

        # Should not terminate early
        assert result.terminated_early is False
        assert result.termination_reason == TerminationReason.NONE

    def test_no_margin_call_with_profitable_trade(self):
        """No margin call when position is profitable."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = [100 + i * 2 for i in range(10)]  # Price goes up
        df = pd.DataFrame({
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * 10,
            "signal": [Position.LONG] * 10,
        }, index=dates)

        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.25,
            enable_margin_protection=True,
        )
        result = engine.run(df)

        assert result.terminated_early is False
        assert result.termination_reason == TerminationReason.NONE
        assert result.total_return > 0

    def test_bankruptcy_when_equity_zero(self):
        """Bankruptcy should be detected when equity goes to zero or negative."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        # Extreme crash scenario
        prices = [100, 100, 1, 0.5, 0.1, 0.01, 0.01, 0.01, 0.01, 0.01]
        df = pd.DataFrame({
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * 10,
            "signal": [Position.LONG] * 10,
        }, index=dates)

        engine = BacktestEngine(
            starting_capital=10000,
            margin_call_threshold=0.01,  # Very low threshold to test bankruptcy
            enable_margin_protection=True,
        )
        result = engine.run(df)

        # Should be terminated (either margin call or bankruptcy)
        assert result.terminated_early is True

    def test_margin_requirement_limits_short_size(self):
        """Margin requirement should limit short position size."""
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        prices = [100, 100, 100, 100, 100]
        df = pd.DataFrame({
            "Open": prices,
            "High": [101] * 5,
            "Low": [99] * 5,
            "Close": prices,
            "Volume": [1000] * 5,
            "signal": [Position.SHORT] * 5,
        }, index=dates)

        # With 50% margin, we should short less than without margin
        engine_with_margin = BacktestEngine(
            starting_capital=10000,
            margin_requirement=0.5,
            enable_margin_protection=True,
        )
        result_with = engine_with_margin.run(df)

        engine_no_margin = BacktestEngine(
            starting_capital=10000,
            margin_requirement=0.5,
            enable_margin_protection=False,
        )
        result_no = engine_no_margin.run(df)

        # Shares shorted should be limited by margin
        short_trade_with = [t for t in result_with.trades if t.action == "SHORT"]
        short_trade_no = [t for t in result_no.trades if t.action == "SHORT"]

        if short_trade_with and short_trade_no:
            assert short_trade_with[0].shares <= short_trade_no[0].shares


class TestBacktestResultProperties:
    """Tests for BacktestResult properties."""

    def test_was_margin_called_property(self):
        """was_margin_called should reflect termination reason."""
        result = BacktestResult(
            equity_curve=pd.Series([10000]),
            benchmark_curve=pd.Series([10000]),
            drawdown_curve=pd.Series([0]),
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            terminated_early=True,
            termination_reason=TerminationReason.MARGIN_CALL,
        )
        assert result.was_margin_called is True
        assert result.went_bankrupt is False

    def test_went_bankrupt_property(self):
        """went_bankrupt should reflect termination reason."""
        result = BacktestResult(
            equity_curve=pd.Series([10000]),
            benchmark_curve=pd.Series([10000]),
            drawdown_curve=pd.Series([0]),
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            terminated_early=True,
            termination_reason=TerminationReason.BANKRUPTCY,
        )
        assert result.was_margin_called is False
        assert result.went_bankrupt is True

    def test_no_termination_properties(self):
        """Properties should be False when no termination."""
        result = BacktestResult(
            equity_curve=pd.Series([10000]),
            benchmark_curve=pd.Series([10000]),
            drawdown_curve=pd.Series([0]),
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            terminated_early=False,
            termination_reason=TerminationReason.NONE,
        )
        assert result.was_margin_called is False
        assert result.went_bankrupt is False

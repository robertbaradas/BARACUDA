"""Unit tests for open position tracking and reporting."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime

from src.backtesting.engine import BacktestEngine, BacktestResult, OpenPosition, Trade
from src.strategies.base_strategy import Position


class TestOpenPosition:
    """Tests for OpenPosition dataclass."""

    def test_is_winning_positive_pnl(self):
        """Positive unrealized P&L is winning."""
        pos = OpenPosition(
            direction="LONG",
            shares=100,
            entry_price=50.0,
            entry_date=datetime(2023, 1, 1),
            current_price=55.0,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=10.0,
        )
        assert pos.is_winning is True

    def test_is_winning_negative_pnl(self):
        """Negative unrealized P&L is losing."""
        pos = OpenPosition(
            direction="LONG",
            shares=100,
            entry_price=50.0,
            entry_date=datetime(2023, 1, 1),
            current_price=45.0,
            unrealized_pnl=-500.0,
            unrealized_pnl_pct=-10.0,
        )
        assert pos.is_winning is False

    def test_is_winning_zero_pnl(self):
        """Zero P&L is not winning."""
        pos = OpenPosition(
            direction="LONG",
            shares=100,
            entry_price=50.0,
            entry_date=datetime(2023, 1, 1),
            current_price=50.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
        )
        assert pos.is_winning is False


class TestBacktestResultOpenPosition:
    """Tests for BacktestResult open position properties."""

    @pytest.fixture
    def sample_result_with_open_position(self):
        """Create a sample result with an open position."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        equity = pd.Series([10000] * 10, index=dates)
        benchmark = pd.Series([10000] * 10, index=dates)
        drawdown = pd.Series([0] * 10, index=dates)

        open_pos = OpenPosition(
            direction="LONG",
            shares=100,
            entry_price=100.0,
            entry_date=dates[5],
            current_price=95.0,
            unrealized_pnl=-500.0,
            unrealized_pnl_pct=-5.0,
        )

        return BacktestResult(
            equity_curve=equity,
            benchmark_curve=benchmark,
            drawdown_curve=drawdown,
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=1,
            win_rate=100.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=float("inf"),
            trades=[],
            open_position=open_pos,
            adjusted_win_rate=0.0,
        )

    @pytest.fixture
    def sample_result_no_open_position(self):
        """Create a sample result without an open position."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        equity = pd.Series([10000] * 10, index=dates)
        benchmark = pd.Series([10000] * 10, index=dates)
        drawdown = pd.Series([0] * 10, index=dates)

        return BacktestResult(
            equity_curve=equity,
            benchmark_curve=benchmark,
            drawdown_curve=drawdown,
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=2,
            win_rate=50.0,
            avg_win=100.0,
            avg_loss=-100.0,
            profit_factor=1.0,
            trades=[],
            open_position=None,
            adjusted_win_rate=None,
        )

    def test_has_open_position_true(self, sample_result_with_open_position):
        """has_open_position returns True when position exists."""
        assert sample_result_with_open_position.has_open_position is True

    def test_has_open_position_false(self, sample_result_no_open_position):
        """has_open_position returns False when no position."""
        assert sample_result_no_open_position.has_open_position is False


class TestBacktestEngineOpenPosition:
    """Tests for BacktestEngine open position detection."""

    @pytest.fixture
    def engine(self):
        """Create a backtest engine."""
        return BacktestEngine(starting_capital=10000, commission=0, slippage=0)

    @pytest.fixture
    def sample_df_ending_long(self):
        """Create data that ends with a LONG signal (open position)."""
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=20, freq="D")
        close = 100 + np.cumsum(np.random.randn(20))

        df = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": [1000] * 20,
                "signal": [Position.FLAT.value] * 10 + [Position.LONG.value] * 10,
            },
            index=dates,
        )
        return df

    @pytest.fixture
    def sample_df_closed_position(self):
        """Create data where position is closed at end."""
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=20, freq="D")
        close = 100 + np.cumsum(np.random.randn(20))

        # FLAT -> LONG -> FLAT (position opened and closed)
        signals = (
            [Position.FLAT.value] * 5
            + [Position.LONG.value] * 10
            + [Position.FLAT.value] * 5
        )

        df = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": [1000] * 20,
                "signal": signals,
            },
            index=dates,
        )
        return df

    def test_detects_open_long_position(self, engine, sample_df_ending_long):
        """Engine detects open LONG position at end."""
        result = engine.run(sample_df_ending_long, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is True
        assert result.open_position.direction == "LONG"
        assert result.open_position.shares > 0

    def test_no_open_position_when_closed(self, engine, sample_df_closed_position):
        """Engine reports no open position when position is closed."""
        result = engine.run(sample_df_closed_position, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is False
        assert result.open_position is None

    def test_open_position_unrealized_pnl_calculation(self, engine):
        """Unrealized P&L is calculated correctly."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        # Price goes from 100 to 90 (10% drop)
        close = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 95.0, 92.0, 91.0, 90.0, 90.0])

        df = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": [1000] * 10,
                # Buy at day 2 (price ~100), hold until end (price 90)
                "signal": [Position.FLAT.value] * 2 + [Position.LONG.value] * 8,
            },
            index=dates,
        )

        result = engine.run(df, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is True
        # Price dropped, so unrealized P&L should be negative
        assert result.open_position.unrealized_pnl < 0
        assert result.open_position.unrealized_pnl_pct < 0

    def test_adjusted_win_rate_calculated(self, engine, sample_df_ending_long):
        """Adjusted win rate is calculated when open position exists."""
        result = engine.run(sample_df_ending_long, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is True
        assert result.adjusted_win_rate is not None

    def test_adjusted_win_rate_none_when_no_open_position(self, engine, sample_df_closed_position):
        """Adjusted win rate is None when no open position."""
        result = engine.run(sample_df_closed_position, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is False
        assert result.adjusted_win_rate is None

    def test_open_short_position_detected(self, engine):
        """Engine detects open SHORT position."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        close = np.array([100.0] * 10)

        df = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": [1000] * 10,
                "signal": [Position.FLAT.value] * 3 + [Position.SHORT.value] * 7,
            },
            index=dates,
        )

        result = engine.run(df, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is True
        assert result.open_position.direction == "SHORT"

    def test_open_position_entry_date_correct(self, engine):
        """Open position records correct entry date."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        close = np.array([100.0] * 10)

        df = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": [1000] * 10,
                "signal": [Position.FLAT.value] * 5 + [Position.LONG.value] * 5,
            },
            index=dates,
        )

        result = engine.run(df, ticker="TEST", strategy_name="Test")

        assert result.has_open_position is True
        # Entry should be at day 5 (index 5) when signal changes to LONG
        assert result.open_position.entry_date == dates[5]


class TestExportServiceOpenPosition:
    """Tests for export service with open positions."""

    @pytest.fixture
    def export_service(self, tmp_path):
        """Create export service with temp directory."""
        from src.services.export_service import ExportService
        return ExportService(output_dir=tmp_path)

    @pytest.fixture
    def result_with_open_position(self):
        """Create a result with an open losing position."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        equity = pd.Series([10000, 10100, 10050, 10200, 10150, 10300, 10250, 10200, 10150, 10100], index=dates)
        benchmark = pd.Series([10000] * 10, index=dates)
        drawdown = pd.Series([0, 0, -0.5, 0, -0.5, 0, -0.5, -1.0, -1.5, -2.0], index=dates)

        trades = [
            Trade(date=dates[1], action="BUY", shares=100, price=100.0, commission=0, equity_after=10100),
        ]

        open_pos = OpenPosition(
            direction="LONG",
            shares=100,
            entry_price=100.0,
            entry_date=dates[1],
            current_price=95.0,
            unrealized_pnl=-500.0,
            unrealized_pnl_pct=-5.0,
        )

        return BacktestResult(
            equity_curve=equity,
            benchmark_curve=benchmark,
            drawdown_curve=drawdown,
            total_return=1.0,
            benchmark_return=0.0,
            excess_return=1.0,
            sharpe_ratio=0.5,
            max_drawdown=-2.0,
            volatility=5.0,
            num_trades=1,
            win_rate=100.0,  # Misleading!
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=float("inf"),  # Misleading!
            trades=trades,
            open_position=open_pos,
            adjusted_win_rate=0.0,  # Real win rate with open position counted
            ticker="TEST",
            start_date=dates[0],
            end_date=dates[-1],
            starting_capital=10000.0,
            strategy_name="TestStrategy",
            parameters={"param1": 10},
        )

    def test_export_includes_open_position_warning(self, export_service, result_with_open_position):
        """Export summary includes open position warning section."""
        filepath = export_service.export_summary(result_with_open_position)
        content = filepath.read_text()

        assert "WARNING: OPEN POSITION AT END OF BACKTEST" in content
        assert "LONG" in content
        assert "100.00" in content  # shares
        assert "$100.00" in content  # entry price
        assert "$95.00" in content  # current price
        assert "$-500.00" in content  # unrealized P&L (negative shows as $-amount)

    def test_export_includes_adjusted_win_rate(self, export_service, result_with_open_position):
        """Export summary includes adjusted win rate."""
        filepath = export_service.export_summary(result_with_open_position)
        content = filepath.read_text()

        assert "Adj. Win Rate:" in content
        assert "0.0%" in content  # adjusted win rate

    def test_export_marks_metrics_with_asterisk(self, export_service, result_with_open_position):
        """Export marks misleading metrics with asterisk."""
        filepath = export_service.export_summary(result_with_open_position)
        content = filepath.read_text()

        # Win rate should have asterisk
        assert "100.0% *" in content
        # Explanation should be present
        assert "Metrics marked with asterisk may be misleading" in content

    def test_export_no_warning_without_open_position(self, export_service):
        """Export summary has no warning when no open position."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        equity = pd.Series([10000] * 10, index=dates)
        benchmark = pd.Series([10000] * 10, index=dates)
        drawdown = pd.Series([0] * 10, index=dates)

        result = BacktestResult(
            equity_curve=equity,
            benchmark_curve=benchmark,
            drawdown_curve=drawdown,
            total_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            volatility=0.0,
            num_trades=2,
            win_rate=50.0,
            avg_win=100.0,
            avg_loss=-100.0,
            profit_factor=1.0,
            trades=[],
            open_position=None,
            adjusted_win_rate=None,
            ticker="TEST",
            start_date=dates[0],
            end_date=dates[-1],
            starting_capital=10000.0,
            strategy_name="TestStrategy",
            parameters={},
        )

        filepath = export_service.export_summary(result)
        content = filepath.read_text()

        assert "WARNING: OPEN POSITION" not in content
        assert "Adj. Win Rate:" not in content

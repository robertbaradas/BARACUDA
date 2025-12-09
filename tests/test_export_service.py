"""Unit tests for export service."""

import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.services.export_service import ExportService
from src.backtesting.engine import BacktestResult, Trade


class TestExportService:
    """Tests for ExportService."""

    @pytest.fixture
    def export_service(self, tmp_path):
        """Create export service with temp directory."""
        return ExportService(output_dir=tmp_path)

    @pytest.fixture
    def sample_result(self):
        """Create sample BacktestResult."""
        import pandas as pd

        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        equity = pd.Series([10000, 10100, 10050, 10200, 10150, 10300, 10250, 10400, 10350, 10500], index=dates)
        benchmark = pd.Series([10000, 10050, 10100, 10150, 10200, 10250, 10300, 10350, 10400, 10450], index=dates)
        drawdown = pd.Series([0, 0, -0.5, 0, -0.5, 0, -0.5, 0, -0.5, 0], index=dates)

        trades = [
            Trade(date=dates[1], action="BUY", shares=100, price=100.0, commission=0, equity_after=10100),
            Trade(date=dates[5], action="SELL", shares=100, price=103.0, commission=0, equity_after=10300),
        ]

        return BacktestResult(
            equity_curve=equity,
            benchmark_curve=benchmark,
            drawdown_curve=drawdown,
            total_return=5.0,
            benchmark_return=4.5,
            excess_return=0.5,
            sharpe_ratio=1.5,
            max_drawdown=-0.5,
            volatility=10.0,
            num_trades=2,
            win_rate=100.0,
            avg_win=300.0,
            avg_loss=0.0,
            profit_factor=float('inf'),
            trades=trades,
            ticker="AAPL",
            start_date=dates[0],
            end_date=dates[-1],
            starting_capital=10000.0,
            strategy_name="RSI",
            parameters={"period": 14, "oversold": 30, "overbought": 70},
        )

    def test_output_dir_created(self, tmp_path):
        """Output directory is created if it doesn't exist."""
        new_dir = tmp_path / "exports"
        service = ExportService(output_dir=new_dir)
        assert new_dir.exists()

    def test_generate_filename(self, export_service):
        """Filename includes ticker, strategy, and timestamp."""
        filepath = export_service.generate_filename("AAPL", "RSI", "txt")
        assert "AAPL" in filepath.name
        assert "RSI" in filepath.name
        assert filepath.suffix == ".txt"

    def test_export_summary_creates_file(self, export_service, sample_result):
        """Export summary creates a text file."""
        filepath = export_service.export_summary(sample_result)
        assert filepath.exists()
        assert filepath.suffix == ".txt"

    def test_export_summary_content(self, export_service, sample_result):
        """Export summary contains expected content."""
        filepath = export_service.export_summary(sample_result)
        content = filepath.read_text()

        assert "AAPL" in content
        assert "RSI" in content
        assert "+5.00%" in content  # total return
        assert "period: 14" in content
        assert "BUY" in content
        assert "SELL" in content

    def test_export_summary_ensemble(self, export_service, sample_result):
        """Export summary handles ensemble parameters."""
        sample_result.strategy_name = "Ensemble(RSI+MACD)"
        sample_result.parameters = {
            "voting_mode": "majority",
            "threshold": 0.5,
            "strategies": [
                {"name": "RSI", "weight": 1.0, "params": {"period": 14}},
                {"name": "MACD", "weight": 1.5, "params": {"fast_period": 12}},
            ]
        }

        filepath = export_service.export_summary(sample_result)
        content = filepath.read_text()

        assert "majority" in content
        assert "RSI" in content
        assert "MACD" in content
        assert "weight: 1.5" in content

    def test_generate_filename_sanitizes_strategy_name(self, export_service):
        """Special characters are removed from strategy name in filename."""
        filepath = export_service.generate_filename("AAPL", "Ensemble(RSI+MACD)", "txt")
        assert "(" not in filepath.name
        assert ")" not in filepath.name
        assert "+" not in filepath.name

    def test_export_summary_no_trades(self, export_service, sample_result):
        """Export summary handles case with no trades."""
        sample_result.trades = []
        sample_result.num_trades = 0
        filepath = export_service.export_summary(sample_result)
        content = filepath.read_text()

        assert "AAPL" in content
        assert "Number of Trades: 0" in content

    def test_export_summary_with_zero_profit_factor(self, export_service, sample_result):
        """Export summary handles profit factor correctly."""
        sample_result.profit_factor = 2.5
        filepath = export_service.export_summary(sample_result)
        content = filepath.read_text()

        assert "Profit Factor:    2.50" in content

    def test_export_summary_infinite_profit_factor(self, export_service, sample_result):
        """Export summary handles infinite profit factor."""
        sample_result.profit_factor = float('inf')
        filepath = export_service.export_summary(sample_result)
        content = filepath.read_text()

        assert "Profit Factor:    Infinite" in content

    def test_default_output_dir(self):
        """Default output directory is in home folder."""
        service = ExportService()
        assert service.output_dir == Path.home() / "BARACUDA_exports"
        # Clean up
        if service.output_dir.exists() and not any(service.output_dir.iterdir()):
            service.output_dir.rmdir()

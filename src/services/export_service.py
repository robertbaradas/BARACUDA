from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtesting.engine import BacktestResult

logger = logging.getLogger(__name__)


class ExportService:
    """Handles exporting backtest results to files."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize export service.

        Args:
            output_dir: Directory for exports. Defaults to user's home/BARACUDA_exports
        """
        if output_dir is None:
            output_dir = Path.home() / "BARACUDA_exports"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_filename(self, ticker: str, strategy_name: str, extension: str) -> Path:
        """Generate a timestamped filename."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_strategy = strategy_name.replace(" ", "_").replace("(", "").replace(")", "").replace("+", "_")
        filename = f"{ticker}_{safe_strategy}_{timestamp}.{extension}"
        return self.output_dir / filename

    def export_summary(self, result: "BacktestResult") -> Path:
        """Export backtest summary as a text file.

        Args:
            result: BacktestResult to export

        Returns:
            Path to the exported file
        """
        filepath = self.generate_filename(result.ticker, result.strategy_name, "txt")

        lines = [
            "=" * 60,
            "BARACUDA Strategy Backtest Report",
            "=" * 60,
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "-" * 60,
            "STUDY PARAMETERS",
            "-" * 60,
            f"Ticker:           {result.ticker}",
            f"Strategy:         {result.strategy_name}",
            f"Start Date:       {result.start_date.strftime('%Y-%m-%d') if result.start_date else 'N/A'}",
            f"End Date:         {result.end_date.strftime('%Y-%m-%d') if result.end_date else 'N/A'}",
            f"Starting Capital: ${result.starting_capital:,.2f}",
            "",
        ]

        # Strategy parameters
        if result.parameters:
            lines.append("Strategy Parameters:")
            if "strategies" in result.parameters:
                # Ensemble
                lines.append(f"  Voting Mode:    {result.parameters.get('voting_mode', 'N/A')}")
                lines.append(f"  Threshold:      {result.parameters.get('threshold', 'N/A')}")
                lines.append("  Strategies:")
                for s in result.parameters.get("strategies", []):
                    lines.append(f"    - {s['name']} (weight: {s.get('weight', 1.0)})")
                    if s.get("params"):
                        for k, v in s["params"].items():
                            lines.append(f"        {k}: {v}")
            else:
                # Single strategy
                for key, value in result.parameters.items():
                    lines.append(f"  {key}: {value}")

        lines.extend([
            "",
            "-" * 60,
            "PERFORMANCE METRICS",
            "-" * 60,
            f"Strategy Return:  {result.total_return:+.2f}%",
            f"Benchmark Return: {result.benchmark_return:+.2f}%",
            f"Excess Return:    {result.excess_return:+.2f}%",
            "",
            f"Sharpe Ratio:     {result.sharpe_ratio:.2f}",
            f"Max Drawdown:     {result.max_drawdown:.2f}%",
            f"Volatility:       {result.volatility:.2f}%",
            "",
            f"Number of Trades: {result.num_trades}",
            f"Win Rate:         {result.win_rate:.1f}%" + (" *" if result.has_open_position else ""),
        ])

        # Add adjusted win rate if there's an open position
        if result.adjusted_win_rate is not None:
            lines.append(f"Adj. Win Rate:    {result.adjusted_win_rate:.1f}% (incl. open position)")

        lines.extend([
            f"Avg Win:          ${result.avg_win:,.2f}" if result.avg_win else "Avg Win:          N/A",
            f"Avg Loss:         ${result.avg_loss:,.2f}" if result.avg_loss else "Avg Loss:         N/A",
            f"Profit Factor:    {result.profit_factor:.2f}" + (" *" if result.has_open_position else "") if result.profit_factor != float('inf') else "Profit Factor:    Infinite" + (" *" if result.has_open_position else ""),
            "",
        ])

        # Open position warning section
        if result.has_open_position:
            pos = result.open_position
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            lines.extend([
                "-" * 60,
                "WARNING: OPEN POSITION AT END OF BACKTEST",
                "-" * 60,
                f"Direction:        {pos.direction}",
                f"Shares:           {pos.shares:.2f}",
                f"Entry Price:      ${pos.entry_price:.2f}",
                f"Entry Date:       {pos.entry_date.strftime('%Y-%m-%d')}",
                f"Current Price:    ${pos.current_price:.2f}",
                f"Unrealized P&L:   {pnl_sign}${pos.unrealized_pnl:,.2f} ({pnl_sign}{pos.unrealized_pnl_pct:.2f}%)",
                "",
                "* Metrics marked with asterisk may be misleading due to open position.",
                "",
            ])

        # Trade list
        if result.trades:
            lines.extend([
                "-" * 60,
                "TRADE HISTORY",
                "-" * 60,
                f"{'Date':<12} {'Action':<8} {'Shares':>10} {'Price':>10} {'Equity':>12}",
                "-" * 60,
            ])
            for trade in result.trades:
                lines.append(
                    f"{trade.date.strftime('%Y-%m-%d'):<12} "
                    f"{trade.action:<8} "
                    f"{trade.shares:>10.2f} "
                    f"${trade.price:>9.2f} "
                    f"${trade.equity_after:>11,.2f}"
                )

        lines.extend([
            "",
            "=" * 60,
            "End of Report",
            "=" * 60,
        ])

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Exported summary to {filepath}")
        return filepath

    def export_chart_png(
        self,
        chart_widget,
        result: "BacktestResult",
    ) -> Path:
        """Export chart widget as PNG image.

        Args:
            chart_widget: BacktestChartWidget to export
            result: BacktestResult for filename

        Returns:
            Path to the exported file
        """
        filepath = self.generate_filename(result.ticker, result.strategy_name, "png")

        # Grab the entire widget as an image
        pixmap = chart_widget.grab()
        pixmap.save(str(filepath), "PNG")

        logger.info(f"Exported chart to {filepath}")
        return filepath

    def export_all(
        self,
        chart_widget,
        result: "BacktestResult",
    ) -> tuple:
        """Export both chart and summary.

        Returns:
            Tuple of (chart_path, summary_path)
        """
        chart_path = self.export_chart_png(chart_widget, result)
        summary_path = self.export_summary(result)
        return chart_path, summary_path

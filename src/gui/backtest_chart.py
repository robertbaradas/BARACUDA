from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from src.backtesting.engine import BacktestResult


class BacktestChartWidget(QtWidgets.QWidget):
    """Lightweight chart widget for displaying backtest results."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the chart layout."""
        pg.setConfigOptions(antialias=True)
        pg.setConfigOption("background", "#1e1e1e")
        pg.setConfigOption("foreground", "#d4d4d4")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Price chart
        self.price_plot = pg.PlotWidget(title="Price")
        self.price_plot.showGrid(x=True, y=True, alpha=0.3)
        self.price_plot.setLabel("left", "Price ($)")
        layout.addWidget(self.price_plot, stretch=2)

        # Equity curve chart
        self.equity_plot = pg.PlotWidget(title="Equity vs Benchmark")
        self.equity_plot.showGrid(x=True, y=True, alpha=0.3)
        self.equity_plot.setLabel("left", "Value ($)")
        self.equity_plot.addLegend()
        layout.addWidget(self.equity_plot, stretch=2)

        # Drawdown chart
        self.drawdown_plot = pg.PlotWidget(title="Drawdown")
        self.drawdown_plot.showGrid(x=True, y=True, alpha=0.3)
        self.drawdown_plot.setLabel("left", "Drawdown (%)")
        layout.addWidget(self.drawdown_plot, stretch=1)

        # RSI subplot (initially hidden)
        self.indicator_plot = pg.PlotWidget(title="Indicator")
        self.indicator_plot.showGrid(x=True, y=True, alpha=0.3)
        self.indicator_plot.setVisible(False)
        layout.addWidget(self.indicator_plot, stretch=1)

        # Link X axes
        self.equity_plot.setXLink(self.price_plot)
        self.drawdown_plot.setXLink(self.price_plot)
        self.indicator_plot.setXLink(self.price_plot)

    def clear(self) -> None:
        """Clear all plots."""
        self.price_plot.clear()
        self.equity_plot.clear()
        self.drawdown_plot.clear()
        self.indicator_plot.clear()

    def plot_results(
        self,
        result: BacktestResult,
        price_data: np.ndarray,
        indicator_data: Optional[np.ndarray] = None,
        indicator_name: str = "Indicator",
        indicator_range: Optional[tuple] = None,
        hlines: Optional[list] = None,
    ) -> None:
        """Plot backtest results.

        Args:
            result: BacktestResult from engine
            price_data: Array of closing prices
            indicator_data: Optional array of indicator values
            indicator_name: Name for indicator subplot
            indicator_range: Y-axis range for indicator (e.g., (0, 100) for RSI)
            hlines: Horizontal lines for indicator [{y, color, label}]
        """
        self.clear()

        n = len(result.equity_curve)
        x = np.arange(n)

        # Price chart
        self.price_plot.plot(
            x, price_data[-n:],
            pen=pg.mkPen("#4fc3f7", width=1.5),
            name="Close",
        )

        # Equity vs Benchmark
        self.equity_plot.plot(
            x, result.equity_curve.values,
            pen=pg.mkPen("#66bb6a", width=2),
            name="Strategy",
        )
        self.equity_plot.plot(
            x, result.benchmark_curve.values,
            pen=pg.mkPen("#ffa726", width=2),
            name="Benchmark",
        )

        # Drawdown
        self.drawdown_plot.plot(
            x, result.drawdown_curve.values,
            pen=pg.mkPen("#ef5350", width=1.5),
            fillLevel=0,
            brush=pg.mkBrush("#ef535050"),
        )

        # Indicator subplot
        if indicator_data is not None:
            self.indicator_plot.setVisible(True)
            self.indicator_plot.setTitle(indicator_name)

            # Plot indicator line
            valid_indicator = indicator_data[-n:]
            self.indicator_plot.plot(
                x, valid_indicator,
                pen=pg.mkPen("#ffd54f", width=1.5),
            )

            # Set Y range if specified
            if indicator_range:
                self.indicator_plot.setYRange(indicator_range[0], indicator_range[1])

            # Add horizontal lines
            if hlines:
                for hl in hlines:
                    line = pg.InfiniteLine(
                        pos=hl["y"],
                        angle=0,
                        pen=pg.mkPen(hl.get("color", "#888888"), style=QtCore.Qt.DashLine),
                    )
                    self.indicator_plot.addItem(line)
        else:
            self.indicator_plot.setVisible(False)

        # Mark trades on price chart
        self._plot_trades(result, price_data[-n:], x)

    def _plot_trades(self, result: BacktestResult, prices: np.ndarray, x: np.ndarray) -> None:
        """Plot trade markers on the price chart."""
        if not result.trades:
            return

        buy_x, buy_y = [], []
        sell_x, sell_y = [], []

        dates = result.equity_curve.index
        for trade in result.trades:
            try:
                idx = dates.get_loc(trade.date)
                if trade.action in ("BUY", "COVER"):
                    buy_x.append(idx)
                    buy_y.append(trade.price)
                elif trade.action in ("SELL", "SHORT"):
                    sell_x.append(idx)
                    sell_y.append(trade.price)
            except KeyError:
                continue

        if buy_x:
            self.price_plot.plot(
                buy_x, buy_y,
                pen=None,
                symbol="t",
                symbolSize=12,
                symbolBrush="#66bb6a",
                symbolPen=None,
            )

        if sell_x:
            self.price_plot.plot(
                sell_x, sell_y,
                pen=None,
                symbol="t1",
                symbolSize=12,
                symbolBrush="#ef5350",
                symbolPen=None,
            )

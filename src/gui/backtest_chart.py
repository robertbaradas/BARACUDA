from __future__ import annotations

from typing import Optional, List, Dict, Any

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from src.backtesting.engine import BacktestResult
from src.strategies.base_strategy import ChartConfig
from src.theme import Colors


class BacktestChartWidget(QtWidgets.QWidget):
    """Lightweight chart widget for displaying backtest results."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the chart layout."""
        pg.setConfigOptions(antialias=True)
        pg.setConfigOption("background", Colors.BG_BASE)
        pg.setConfigOption("foreground", Colors.TEXT_SECONDARY)

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

        # Indicator subplot (dynamically configured)
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
        df: Optional[Any] = None,
        chart_config: Optional[ChartConfig] = None,
        indicator_name: str = "Indicator",
        # Legacy parameters for backward compatibility
        indicator_data: Optional[np.ndarray] = None,
        indicator_range: Optional[tuple] = None,
        hlines: Optional[list] = None,
    ) -> None:
        """Plot backtest results.

        Args:
            result: BacktestResult from engine
            price_data: Array of closing prices
            df: DataFrame with indicator columns (for chart_config-based plotting)
            chart_config: ChartConfig from strategy
            indicator_name: Name for indicator subplot
            indicator_data: Legacy - array of indicator values
            indicator_range: Legacy - Y-axis range for indicator
            hlines: Legacy - horizontal lines
        """
        self.clear()

        n = len(result.equity_curve)
        x = np.arange(n)

        # Price chart
        self.price_plot.plot(
            x, price_data[-n:],
            pen=pg.mkPen(Colors.ACCENT_CYAN, width=1.5),
            name="Close",
        )

        # Overlay indicators on price chart (if not subplot)
        if chart_config is not None and df is not None and not chart_config.subplot:
            self._plot_overlay_indicators(df, chart_config, n)

        # Equity vs Benchmark
        self.equity_plot.plot(
            x, result.equity_curve.values,
            pen=pg.mkPen(Colors.POSITIVE, width=2),
            name="Strategy",
        )
        self.equity_plot.plot(
            x, result.benchmark_curve.values,
            pen=pg.mkPen(Colors.WARNING, width=2),
            name="Benchmark",
        )

        # Drawdown
        self.drawdown_plot.plot(
            x, result.drawdown_curve.values,
            pen=pg.mkPen(Colors.NEGATIVE, width=1.5),
            fillLevel=0,
            brush=pg.mkBrush(Colors.NEGATIVE + "50"),
        )

        # Indicator subplot (only for strategies that use subplots)
        if chart_config is not None and df is not None and chart_config.subplot:
            self._plot_indicator_from_config(df, chart_config, indicator_name, n)
        elif indicator_data is not None:
            # Legacy path
            self._plot_indicator_legacy(indicator_data, indicator_name, indicator_range, hlines, n)
        else:
            # No subplot needed (overlay indicators or no indicator)
            self.indicator_plot.setVisible(False)

        # Mark trades on price chart
        self._plot_trades(result, price_data[-n:], x)

    def _plot_overlay_indicators(self, df: Any, config: ChartConfig, n: int) -> None:
        """Plot indicator lines overlaid on price chart."""
        x = np.arange(n)

        for line in config.lines:
            col = line.get("column")
            if col and col in df.columns:
                data = df[col].values[-n:]
                color = line.get("color", "#ffd54f")
                width = line.get("width", 1)
                self.price_plot.plot(
                    x, data,
                    pen=pg.mkPen(color, width=width),
                    name=line.get("label", col),
                )

    def _plot_indicator_from_config(
        self,
        df: Any,
        config: ChartConfig,
        name: str,
        n: int,
    ) -> None:
        """Plot indicator using ChartConfig specification."""
        if not config.subplot:
            self.indicator_plot.setVisible(False)
            return

        self.indicator_plot.setVisible(True)
        self.indicator_plot.setTitle(name)

        x = np.arange(n)

        # Plot lines
        for line in config.lines:
            col = line.get("column")
            if col and col in df.columns:
                data = df[col].values[-n:]
                color = line.get("color", "#ffd54f")
                width = line.get("width", 1.5)
                self.indicator_plot.plot(
                    x, data,
                    pen=pg.mkPen(color, width=width),
                    name=line.get("label", col),
                )

        # Plot bars (histogram)
        for bar in config.bars:
            col = bar.get("column")
            if col and col in df.columns:
                data = df[col].values[-n:]
                color_pos = bar.get("color_pos", Colors.POSITIVE)
                color_neg = bar.get("color_neg", Colors.NEGATIVE)

                # Separate positive and negative values
                pos_mask = data >= 0
                neg_mask = data < 0

                # Plot positive bars
                if pos_mask.any():
                    pos_x = x[pos_mask]
                    pos_y = data[pos_mask]
                    bar_item = pg.BarGraphItem(
                        x=pos_x, height=pos_y, width=0.6,
                        brush=pg.mkBrush(color_pos),
                        pen=pg.mkPen(color_pos),
                    )
                    self.indicator_plot.addItem(bar_item)

                # Plot negative bars
                if neg_mask.any():
                    neg_x = x[neg_mask]
                    neg_y = data[neg_mask]
                    bar_item = pg.BarGraphItem(
                        x=neg_x, height=neg_y, width=0.6,
                        brush=pg.mkBrush(color_neg),
                        pen=pg.mkPen(color_neg),
                    )
                    self.indicator_plot.addItem(bar_item)

        # Set Y range if specified
        if config.y_range:
            self.indicator_plot.setYRange(config.y_range[0], config.y_range[1])

        # Add horizontal lines
        for hl in config.hlines:
            style_map = {
                "solid": QtCore.Qt.SolidLine,
                "dashed": QtCore.Qt.DashLine,
                "dotted": QtCore.Qt.DotLine,
            }
            style = style_map.get(hl.get("style", "dashed"), QtCore.Qt.DashLine)
            line = pg.InfiniteLine(
                pos=hl["y"],
                angle=0,
                pen=pg.mkPen(hl.get("color", Colors.TEXT_SECONDARY), style=style),
            )
            self.indicator_plot.addItem(line)

    def _plot_indicator_legacy(
        self,
        indicator_data: np.ndarray,
        name: str,
        indicator_range: Optional[tuple],
        hlines: Optional[list],
        n: int,
    ) -> None:
        """Legacy indicator plotting for backward compatibility."""
        self.indicator_plot.setVisible(True)
        self.indicator_plot.setTitle(name)

        x = np.arange(n)
        valid_indicator = indicator_data[-n:]
        self.indicator_plot.plot(
            x, valid_indicator,
            pen=pg.mkPen(Colors.CHART_ORANGE, width=1.5),
        )

        if indicator_range:
            self.indicator_plot.setYRange(indicator_range[0], indicator_range[1])

        if hlines:
            for hl in hlines:
                line = pg.InfiniteLine(
                    pos=hl["y"],
                    angle=0,
                    pen=pg.mkPen(hl.get("color", Colors.TEXT_SECONDARY), style=QtCore.Qt.DashLine),
                )
                self.indicator_plot.addItem(line)

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
                symbolBrush=Colors.POSITIVE,
                symbolPen=None,
            )

        if sell_x:
            self.price_plot.plot(
                sell_x, sell_y,
                pen=None,
                symbol="t1",
                symbolSize=12,
                symbolBrush=Colors.NEGATIVE,
                symbolPen=None,
            )

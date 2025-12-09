from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.backtesting.engine import BacktestResult


class BacktestResultsPanel(QtWidgets.QWidget):
    """Panel displaying backtest performance metrics."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the results panel layout."""
        layout = QtWidgets.QVBoxLayout(self)

        # Metrics group
        metrics_group = QtWidgets.QGroupBox("Performance Metrics")
        metrics_layout = QtWidgets.QFormLayout()

        self.lbl_strategy_return = QtWidgets.QLabel("—")
        self.lbl_benchmark_return = QtWidgets.QLabel("—")
        self.lbl_excess_return = QtWidgets.QLabel("—")
        self.lbl_sharpe = QtWidgets.QLabel("—")
        self.lbl_max_drawdown = QtWidgets.QLabel("—")
        self.lbl_volatility = QtWidgets.QLabel("—")
        self.lbl_num_trades = QtWidgets.QLabel("—")
        self.lbl_win_rate = QtWidgets.QLabel("—")
        self.lbl_profit_factor = QtWidgets.QLabel("—")

        metrics_layout.addRow("Strategy Return:", self.lbl_strategy_return)
        metrics_layout.addRow("Benchmark Return:", self.lbl_benchmark_return)
        metrics_layout.addRow("Excess Return:", self.lbl_excess_return)
        metrics_layout.addRow("Sharpe Ratio:", self.lbl_sharpe)
        metrics_layout.addRow("Max Drawdown:", self.lbl_max_drawdown)
        metrics_layout.addRow("Volatility:", self.lbl_volatility)
        metrics_layout.addRow("# Trades:", self.lbl_num_trades)
        metrics_layout.addRow("Win Rate:", self.lbl_win_rate)
        metrics_layout.addRow("Profit Factor:", self.lbl_profit_factor)

        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group)

        # Trade list
        trades_group = QtWidgets.QGroupBox("Recent Trades")
        trades_layout = QtWidgets.QVBoxLayout()

        self.trade_table = QtWidgets.QTableWidget()
        self.trade_table.setColumnCount(5)
        self.trade_table.setHorizontalHeaderLabels(["Date", "Action", "Shares", "Price", "Equity"])
        self.trade_table.horizontalHeader().setStretchLastSection(True)
        self.trade_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.trade_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.trade_table.setMaximumHeight(200)

        trades_layout.addWidget(self.trade_table)
        trades_group.setLayout(trades_layout)
        layout.addWidget(trades_group)

        layout.addStretch()

    def clear(self) -> None:
        """Clear all displayed results."""
        self.lbl_strategy_return.setText("—")
        self.lbl_benchmark_return.setText("—")
        self.lbl_excess_return.setText("—")
        self.lbl_sharpe.setText("—")
        self.lbl_max_drawdown.setText("—")
        self.lbl_volatility.setText("—")
        self.lbl_num_trades.setText("—")
        self.lbl_win_rate.setText("—")
        self.lbl_profit_factor.setText("—")
        self.trade_table.setRowCount(0)

    def update_results(self, result: BacktestResult) -> None:
        """Update panel with backtest results."""
        # Format and color returns
        self._set_return_label(self.lbl_strategy_return, result.total_return)
        self._set_return_label(self.lbl_benchmark_return, result.benchmark_return)
        self._set_return_label(self.lbl_excess_return, result.excess_return)

        # Other metrics
        self.lbl_sharpe.setText(f"{result.sharpe_ratio:.2f}")
        self._color_label(self.lbl_sharpe, result.sharpe_ratio, threshold=0)

        self.lbl_max_drawdown.setText(f"{result.max_drawdown:.2f}%")
        self.lbl_max_drawdown.setStyleSheet("color: #ef5350;")  # Always red

        self.lbl_volatility.setText(f"{result.volatility:.2f}%")
        self.lbl_num_trades.setText(str(result.num_trades))

        self.lbl_win_rate.setText(f"{result.win_rate:.1f}%")
        self._color_label(self.lbl_win_rate, result.win_rate, threshold=50)

        if result.profit_factor == float('inf'):
            self.lbl_profit_factor.setText("∞")
            self.lbl_profit_factor.setStyleSheet("color: #66bb6a;")
        else:
            self.lbl_profit_factor.setText(f"{result.profit_factor:.2f}")
            self._color_label(self.lbl_profit_factor, result.profit_factor, threshold=1)

        # Populate trade table
        self._populate_trades(result)

    def _set_return_label(self, label: QtWidgets.QLabel, value: float) -> None:
        """Set return label with color coding."""
        label.setText(f"{value:+.2f}%")
        self._color_label(label, value, threshold=0)

    def _color_label(self, label: QtWidgets.QLabel, value: float, threshold: float) -> None:
        """Color label green if above threshold, red if below."""
        if value > threshold:
            label.setStyleSheet("color: #66bb6a;")
        elif value < threshold:
            label.setStyleSheet("color: #ef5350;")
        else:
            label.setStyleSheet("color: #d4d4d4;")

    def _populate_trades(self, result: BacktestResult) -> None:
        """Fill trade table with recent trades."""
        trades = result.trades[-20:]  # Show last 20 trades
        self.trade_table.setRowCount(len(trades))

        for i, trade in enumerate(trades):
            self.trade_table.setItem(i, 0, QtWidgets.QTableWidgetItem(
                trade.date.strftime("%Y-%m-%d")
            ))

            action_item = QtWidgets.QTableWidgetItem(trade.action)
            if trade.action in ("BUY", "COVER"):
                action_item.setForeground(QtGui.QColor("#66bb6a"))
            else:
                action_item.setForeground(QtGui.QColor("#ef5350"))
            self.trade_table.setItem(i, 1, action_item)

            self.trade_table.setItem(i, 2, QtWidgets.QTableWidgetItem(
                f"{trade.shares:.2f}"
            ))
            self.trade_table.setItem(i, 3, QtWidgets.QTableWidgetItem(
                f"${trade.price:.2f}"
            ))
            self.trade_table.setItem(i, 4, QtWidgets.QTableWidgetItem(
                f"${trade.equity_after:,.2f}"
            ))

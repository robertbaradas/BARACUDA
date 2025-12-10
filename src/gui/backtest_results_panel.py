from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.backtesting.engine import BacktestResult, TerminationReason


class BacktestResultsPanel(QtWidgets.QWidget):
    """Panel displaying backtest performance metrics."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the results panel layout."""
        layout = QtWidgets.QVBoxLayout(self)

        # Open position warning (initially hidden)
        self.open_position_warning = QtWidgets.QFrame()
        self.open_position_warning.setStyleSheet("""
            QFrame {
                background-color: #4a3000;
                border: 1px solid #ffa726;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        warning_layout = QtWidgets.QVBoxLayout(self.open_position_warning)
        warning_layout.setContentsMargins(8, 8, 8, 8)

        warning_title = QtWidgets.QLabel("Open Position at End")
        warning_title.setStyleSheet("color: #ffa726; font-weight: bold;")
        warning_layout.addWidget(warning_title)

        self.lbl_open_position_details = QtWidgets.QLabel("")
        self.lbl_open_position_details.setStyleSheet("color: #ffcc80;")
        self.lbl_open_position_details.setWordWrap(True)
        self.lbl_open_position_details.setTextFormat(QtCore.Qt.RichText)  # Enable HTML rendering
        warning_layout.addWidget(self.lbl_open_position_details)

        self.open_position_warning.setVisible(False)
        layout.addWidget(self.open_position_warning)

        # Limited data warning (initially hidden)
        self.data_warning = QtWidgets.QFrame()
        self.data_warning.setStyleSheet("""
            QFrame {
                background-color: #3d2000;
                border: 1px solid #ff9800;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        data_warning_layout = QtWidgets.QVBoxLayout(self.data_warning)
        data_warning_layout.setContentsMargins(8, 8, 8, 8)

        data_warning_title = QtWidgets.QLabel("Limited Historical Data")
        data_warning_title.setStyleSheet("color: #ff9800; font-weight: bold;")
        data_warning_layout.addWidget(data_warning_title)

        self.lbl_data_warning_details = QtWidgets.QLabel("")
        self.lbl_data_warning_details.setStyleSheet("color: #ffcc80;")
        self.lbl_data_warning_details.setWordWrap(True)
        data_warning_layout.addWidget(self.lbl_data_warning_details)

        self.data_warning.setVisible(False)
        layout.addWidget(self.data_warning)

        # Termination warning (initially hidden)
        self.termination_warning = QtWidgets.QFrame()
        self.termination_warning.setObjectName("termination_warning")
        termination_warning_layout = QtWidgets.QVBoxLayout(self.termination_warning)
        termination_warning_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_termination_title = QtWidgets.QLabel("")
        self.lbl_termination_title.setStyleSheet("font-weight: bold;")
        termination_warning_layout.addWidget(self.lbl_termination_title)

        self.lbl_termination_details = QtWidgets.QLabel("")
        self.lbl_termination_details.setWordWrap(True)
        self.lbl_termination_details.setTextFormat(QtCore.Qt.RichText)
        termination_warning_layout.addWidget(self.lbl_termination_details)

        self.termination_warning.setVisible(False)
        layout.addWidget(self.termination_warning)

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
        self.lbl_adjusted_win_rate = QtWidgets.QLabel("—")
        self.lbl_profit_factor = QtWidgets.QLabel("—")

        metrics_layout.addRow("Strategy Return:", self.lbl_strategy_return)
        metrics_layout.addRow("Benchmark Return:", self.lbl_benchmark_return)
        metrics_layout.addRow("Excess Return:", self.lbl_excess_return)
        metrics_layout.addRow("Sharpe Ratio:", self.lbl_sharpe)
        metrics_layout.addRow("Max Drawdown:", self.lbl_max_drawdown)
        metrics_layout.addRow("Volatility:", self.lbl_volatility)
        metrics_layout.addRow("# Trades:", self.lbl_num_trades)
        metrics_layout.addRow("Win Rate:", self.lbl_win_rate)
        metrics_layout.addRow("Adj. Win Rate:", self.lbl_adjusted_win_rate)
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
        self.open_position_warning.setVisible(False)
        self.lbl_open_position_details.setText("")
        self.data_warning.setVisible(False)
        self.lbl_data_warning_details.setText("")
        self.termination_warning.setVisible(False)
        self.lbl_termination_title.setText("")
        self.lbl_termination_details.setText("")
        self.lbl_strategy_return.setText("—")
        self.lbl_benchmark_return.setText("—")
        self.lbl_excess_return.setText("—")
        self.lbl_sharpe.setText("—")
        self.lbl_max_drawdown.setText("—")
        self.lbl_volatility.setText("—")
        self.lbl_num_trades.setText("—")
        self.lbl_win_rate.setText("—")
        self.lbl_adjusted_win_rate.setText("—")
        self.lbl_profit_factor.setText("—")
        self.trade_table.setRowCount(0)

    def update_results(self, result: BacktestResult) -> None:
        """Update panel with backtest results."""
        # Handle limited data warning
        if result.data_limited:
            coverage = result.data_coverage_pct
            details = (
                f"Requested {result.days_requested} days, only {result.days_available} available ({coverage:.1f}%).\n"
                f"Stock may have IPO'd recently. Results may not be representative."
            )
            self.lbl_data_warning_details.setText(details)
            self.data_warning.setVisible(True)
        else:
            self.data_warning.setVisible(False)

        # Handle termination warning (bankruptcy or margin call)
        if result.terminated_early:
            if result.termination_reason == TerminationReason.BANKRUPTCY:
                # Red styling for bankruptcy
                self.termination_warning.setStyleSheet("""
                    QFrame {
                        background-color: #4a0000;
                        border: 2px solid #ef5350;
                        border-radius: 4px;
                        padding: 8px;
                    }
                """)
                self.lbl_termination_title.setText("⚠ BANKRUPTCY - Trading Terminated")
                self.lbl_termination_title.setStyleSheet("color: #ef5350; font-weight: bold;")
                self.lbl_termination_details.setStyleSheet("color: #ffcdd2;")
            else:  # MARGIN_CALL
                # Orange styling for margin call
                self.termination_warning.setStyleSheet("""
                    QFrame {
                        background-color: #4a3000;
                        border: 2px solid #ff9800;
                        border-radius: 4px;
                        padding: 8px;
                    }
                """)
                self.lbl_termination_title.setText("⚠ MARGIN CALL - Positions Liquidated")
                self.lbl_termination_title.setStyleSheet("color: #ff9800; font-weight: bold;")
                self.lbl_termination_details.setStyleSheet("color: #ffe0b2;")

            # Format termination date
            term_date = result.termination_date.strftime("%Y-%m-%d") if result.termination_date else "Unknown"
            term_equity = result.termination_equity if result.termination_equity is not None else 0

            details = (
                f"<b>Date:</b> {term_date}<br>"
                f"<b>Final Equity:</b> ${term_equity:,.2f}<br>"
                f"<b>Details:</b> {result.termination_details}"
            )
            self.lbl_termination_details.setText(details)
            self.termination_warning.setVisible(True)
        else:
            self.termination_warning.setVisible(False)

        # Handle open position warning
        if result.has_open_position:
            pos = result.open_position
            pnl_color = "#66bb6a" if pos.is_winning else "#ef5350"
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            details = (
                f"{pos.direction} {pos.shares:.2f} shares @ ${pos.entry_price:.2f}<br>"
                f"Current: ${pos.current_price:.2f}<br>"
                f"Unrealized P&L: <span style='color:{pnl_color}'>{pnl_sign}${pos.unrealized_pnl:,.2f} ({pnl_sign}{pos.unrealized_pnl_pct:.2f}%)</span>"
            )
            self.lbl_open_position_details.setText(details)
            self.open_position_warning.setVisible(True)
        else:
            self.open_position_warning.setVisible(False)

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

        # Win rate - add asterisk if there's an open position
        win_rate_text = f"{result.win_rate:.1f}%"
        if result.has_open_position:
            win_rate_text += " *"
        self.lbl_win_rate.setText(win_rate_text)
        self._color_label(self.lbl_win_rate, result.win_rate, threshold=50)

        # Adjusted win rate (only shown if there's an open position)
        if result.adjusted_win_rate is not None:
            self.lbl_adjusted_win_rate.setText(f"{result.adjusted_win_rate:.1f}%")
            self._color_label(self.lbl_adjusted_win_rate, result.adjusted_win_rate, threshold=50)
        else:
            self.lbl_adjusted_win_rate.setText("—")
            self.lbl_adjusted_win_rate.setStyleSheet("color: #d4d4d4;")

        if result.profit_factor == float('inf'):
            pf_text = "∞"
            if result.has_open_position:
                pf_text += " *"
            self.lbl_profit_factor.setText(pf_text)
            self.lbl_profit_factor.setStyleSheet("color: #66bb6a;")
        else:
            pf_text = f"{result.profit_factor:.2f}"
            if result.has_open_position:
                pf_text += " *"
            self.lbl_profit_factor.setText(pf_text)
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
            if trade.action in ("FORCED_SELL", "FORCED_COVER"):
                # Forced liquidation - orange color
                action_item.setForeground(QtGui.QColor("#ff9800"))
            elif trade.action in ("BUY", "COVER"):
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

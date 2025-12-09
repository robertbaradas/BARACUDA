from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from src.services.backtest_service import BacktestService
from src.services.export_service import ExportService
from src.services.market_data_service import MarketDataService
from src.strategies import create_strategy, get_available_strategies
from src.strategies.ensemble_strategy import VotingMode
from src.gui.backtest_chart import BacktestChartWidget
from src.gui.backtest_results_panel import BacktestResultsPanel
from src.gui.ensemble_panel import EnsemblePanel
from src.gui.strategy_config_widget import StrategyConfigWidget
from src.gui.strategy_selector import StrategySelectorBar
from src.gui.collapsible_panel import CollapsiblePanel

logger = logging.getLogger(__name__)


class BacktestWindow(QtWidgets.QWidget):
    """Main window for strategy backtesting."""

    def __init__(
        self,
        market_data: MarketDataService,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.market_data = market_data
        self.backtest_service = BacktestService(market_data)
        self.export_service = ExportService()
        self._last_result = None
        self._last_df = None
        self._current_strategy_name: str = ""
        self._strategy_config_widget: Optional[StrategyConfigWidget] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the backtest window layout."""
        self.setWindowTitle("Strategy Backtester")
        self.setMinimumSize(1200, 800)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Strategy selector bar at top
        self.strategy_selector = StrategySelectorBar()
        self.strategy_selector.strategySelected.connect(self._on_strategy_selected)
        main_layout.addWidget(self.strategy_selector)

        # Main horizontal splitter: charts | control panel
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3d3d3d;
            }
            QSplitter::handle:hover {
                background-color: #1976d2;
            }
        """)

        # Left side: Charts
        self.chart_widget = BacktestChartWidget()
        self.main_splitter.addWidget(self.chart_widget)

        # Right side: Control panel with vertical splitter for resizable sections
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Vertical splitter for control panel sections
        self.control_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.control_splitter.setHandleWidth(4)
        self.control_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3d3d3d;
            }
            QSplitter::handle:hover {
                background-color: #1976d2;
            }
        """)

        # --- Study Parameters Section ---
        self.params_panel = CollapsiblePanel("Study Parameters")
        params_content = QtWidgets.QWidget()
        params_layout = QtWidgets.QFormLayout(params_content)
        params_layout.setContentsMargins(8, 8, 8, 8)

        self.txt_ticker = QtWidgets.QLineEdit()
        self.txt_ticker.setPlaceholderText("e.g., AAPL")
        self.txt_ticker.setText("SPY")

        self.spin_days = QtWidgets.QSpinBox()
        self.spin_days.setRange(30, 2000)
        self.spin_days.setValue(365)

        self.spin_capital = QtWidgets.QDoubleSpinBox()
        self.spin_capital.setRange(1000, 10000000)
        self.spin_capital.setValue(10000)
        self.spin_capital.setPrefix("$")
        self.spin_capital.setGroupSeparatorShown(True)

        self.spin_commission = QtWidgets.QDoubleSpinBox()
        self.spin_commission.setRange(0, 100)
        self.spin_commission.setValue(0)
        self.spin_commission.setPrefix("$")

        self.spin_slippage = QtWidgets.QDoubleSpinBox()
        self.spin_slippage.setRange(0, 5)
        self.spin_slippage.setValue(0)
        self.spin_slippage.setSuffix("%")
        self.spin_slippage.setDecimals(2)
        self.spin_slippage.setSingleStep(0.1)

        params_layout.addRow("Ticker:", self.txt_ticker)
        params_layout.addRow("Days:", self.spin_days)
        params_layout.addRow("Starting Capital:", self.spin_capital)
        params_layout.addRow("Commission:", self.spin_commission)
        params_layout.addRow("Slippage:", self.spin_slippage)

        self.params_panel.set_content(params_content)
        self.control_splitter.addWidget(self.params_panel)

        # --- Strategy Config Section ---
        self.strategy_panel = CollapsiblePanel("Strategy Parameters")
        self._strategy_config_container = QtWidgets.QWidget()
        self._strategy_config_layout = QtWidgets.QVBoxLayout(self._strategy_config_container)
        self._strategy_config_layout.setContentsMargins(8, 8, 8, 8)
        self.strategy_panel.set_content(self._strategy_config_container)
        self.control_splitter.addWidget(self.strategy_panel)

        # --- Ensemble Section ---
        self.ensemble_panel_wrapper = CollapsiblePanel(
            "Ensemble Configuration", initially_collapsed=True
        )
        self.ensemble_panel = EnsemblePanel()
        self.ensemble_panel.ensembleChanged.connect(self._on_ensemble_changed)
        self.ensemble_panel_wrapper.set_content(self.ensemble_panel)
        self.control_splitter.addWidget(self.ensemble_panel_wrapper)

        # --- Actions Section (Run + Export) ---
        self.actions_panel = CollapsiblePanel("Actions")
        actions_content = QtWidgets.QWidget()
        actions_layout = QtWidgets.QVBoxLayout(actions_content)
        actions_layout.setContentsMargins(8, 8, 8, 8)

        self.btn_run = QtWidgets.QPushButton("Run Backtest")
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        self.btn_run.clicked.connect(self._run_backtest)
        actions_layout.addWidget(self.btn_run)

        # Export buttons
        export_layout = QtWidgets.QHBoxLayout()
        self.btn_export_chart = QtWidgets.QPushButton("Chart")
        self.btn_export_chart.setEnabled(False)
        self.btn_export_chart.clicked.connect(self._export_chart)
        export_layout.addWidget(self.btn_export_chart)

        self.btn_export_summary = QtWidgets.QPushButton("Summary")
        self.btn_export_summary.setEnabled(False)
        self.btn_export_summary.clicked.connect(self._export_summary)
        export_layout.addWidget(self.btn_export_summary)

        self.btn_export_all = QtWidgets.QPushButton("Export All")
        self.btn_export_all.setEnabled(False)
        self.btn_export_all.clicked.connect(self._export_all)
        export_layout.addWidget(self.btn_export_all)

        actions_layout.addLayout(export_layout)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: #888888;")
        self.lbl_status.setWordWrap(True)
        actions_layout.addWidget(self.lbl_status)

        self.actions_panel.set_content(actions_content)
        self.control_splitter.addWidget(self.actions_panel)

        # --- Results Section ---
        self.results_panel_wrapper = CollapsiblePanel("Results")
        self.results_panel = BacktestResultsPanel()
        self.results_panel_wrapper.set_content(self.results_panel)
        self.control_splitter.addWidget(self.results_panel_wrapper)

        # Add control splitter to right panel
        right_layout.addWidget(self.control_splitter)

        # Add right panel to main splitter
        self.main_splitter.addWidget(right_panel)

        # Set initial splitter proportions (charts get ~65%, controls get ~35%)
        self.main_splitter.setSizes([700, 400])

        # Set initial control panel proportions
        self.control_splitter.setSizes([100, 120, 80, 80, 300])

        main_layout.addWidget(self.main_splitter)

        # Initialize with first strategy
        strategies = get_available_strategies()
        if strategies:
            self._on_strategy_selected(strategies[0])

    def _on_strategy_selected(self, strategy_name: str) -> None:
        """Handle strategy selection change."""
        self._current_strategy_name = strategy_name

        # Remove old config widget
        if self._strategy_config_widget is not None:
            self._strategy_config_layout.removeWidget(self._strategy_config_widget)
            self._strategy_config_widget.deleteLater()
            self._strategy_config_widget = None

        # Create new config widget for selected strategy
        strategy = create_strategy(strategy_name)
        self._strategy_config_widget = StrategyConfigWidget(strategy)
        self._strategy_config_layout.addWidget(self._strategy_config_widget)

        # Update panel title
        self.strategy_panel.set_title(f"Strategy: {strategy.display_name}")

        # Clear previous results
        self.chart_widget.clear()
        self.results_panel.clear()
        self._set_status(f"Selected strategy: {strategy.display_name}")

    def _on_ensemble_changed(self) -> None:
        """Handle ensemble configuration change."""
        self.chart_widget.clear()
        self.results_panel.clear()

        if self.ensemble_panel.is_ensemble_enabled():
            self._set_status("Ensemble mode enabled")
        else:
            self._set_status(f"Single strategy: {self._current_strategy_name}")

    def _run_backtest(self) -> None:
        """Execute backtest with current parameters."""
        ticker = self.txt_ticker.text().strip().upper()
        if not ticker:
            self._set_status("Please enter a ticker symbol.", error=True)
            return

        self.btn_run.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        try:
            if self.ensemble_panel.is_ensemble_enabled():
                self._run_ensemble_backtest(ticker)
            else:
                self._run_single_backtest(ticker)

        except Exception as exc:
            logger.exception("Backtest failed")
            self._set_status(f"Error: {exc}", error=True)

        finally:
            self.btn_run.setEnabled(True)

    def _run_single_backtest(self, ticker: str) -> None:
        """Run backtest for a single strategy."""
        if not self._current_strategy_name:
            self._set_status("Please select a strategy.", error=True)
            return

        self._set_status(f"Running {self._current_strategy_name} backtest for {ticker}...")
        QtWidgets.QApplication.processEvents()

        strategy_params = {}
        if self._strategy_config_widget:
            strategy_params = self._strategy_config_widget.get_parameters()

        result = self.backtest_service.run_backtest(
            ticker=ticker,
            strategy_name=self._current_strategy_name,
            days=self.spin_days.value(),
            starting_capital=self.spin_capital.value(),
            commission=self.spin_commission.value(),
            slippage=self.spin_slippage.value() / 100,
            strategy_params=strategy_params,
        )

        self._last_result = result

        strategy = create_strategy(self._current_strategy_name, **strategy_params)
        df = self._fetch_data_for_plotting(ticker, self.spin_days.value())
        df = strategy.run(df)
        self._last_df = df

        chart_config = strategy.get_chart_config()

        self.chart_widget.plot_results(
            result=result,
            price_data=df["Close"].values,
            df=df,
            chart_config=chart_config,
            indicator_name=self._current_strategy_name,
        )

        self.results_panel.update_results(result)
        self._enable_export_buttons(True)

        self._set_status(
            f"Backtest complete: {result.total_return:+.2f}% return, "
            f"{result.num_trades} trades",
            error=False,
        )

    def _run_ensemble_backtest(self, ticker: str) -> None:
        """Run backtest for ensemble of strategies."""
        selected = self.ensemble_panel.get_selected_strategies()
        if len(selected) < 2:
            self._set_status("Ensemble requires at least 2 strategies.", error=True)
            return

        weights = self.ensemble_panel.get_weights()
        voting_mode = self.ensemble_panel.get_voting_mode()
        threshold = self.ensemble_panel.get_threshold()

        self._set_status(f"Running ensemble backtest ({', '.join(selected)}) for {ticker}...")
        QtWidgets.QApplication.processEvents()

        strategy_configs = [
            {"name": name, "params": {}, "weight": weights.get(name, 1.0)}
            for name in selected
        ]

        result = self.backtest_service.run_ensemble_backtest(
            ticker=ticker,
            strategy_configs=strategy_configs,
            voting_mode=voting_mode,
            threshold=threshold,
            days=self.spin_days.value(),
            starting_capital=self.spin_capital.value(),
            commission=self.spin_commission.value(),
            slippage=self.spin_slippage.value() / 100,
        )

        self._last_result = result
        self._last_df = None

        df = self._fetch_data_for_plotting(ticker, self.spin_days.value())
        self.chart_widget.plot_results(
            result=result,
            price_data=df["Close"].values,
            df=None,
            chart_config=None,
            indicator_name="Ensemble",
        )

        self.results_panel.update_results(result)
        self._enable_export_buttons(True)

        self._set_status(
            f"Ensemble backtest complete: {result.total_return:+.2f}% return, "
            f"{result.num_trades} trades",
            error=False,
        )

    def _fetch_data_for_plotting(self, ticker: str, days: int):
        """Fetch data for chart plotting."""
        from datetime import datetime, timedelta
        import pandas as pd

        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(days * 1.5))
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        raw = self.market_data.get_daily_aggs_range(ticker, start_str, end_str)
        results = raw.get("results", [])

        records = []
        for r in results:
            records.append({
                "Date": pd.to_datetime(r["t"], unit="ms"),
                "Open": r["o"],
                "High": r["h"],
                "Low": r["l"],
                "Close": r["c"],
                "Volume": r["v"],
            })

        df = pd.DataFrame(records)
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)

        if len(df) > days:
            df = df.iloc[-days:]

        return df

    def _set_status(self, message: str, error: bool = False) -> None:
        """Update status label."""
        color = "#ef5350" if error else "#66bb6a"
        self.lbl_status.setStyleSheet(f"color: {color};")
        self.lbl_status.setText(message)

    def _enable_export_buttons(self, enabled: bool) -> None:
        """Enable or disable export buttons."""
        self.btn_export_chart.setEnabled(enabled)
        self.btn_export_summary.setEnabled(enabled)
        self.btn_export_all.setEnabled(enabled)

    def _export_chart(self) -> None:
        """Export chart as PNG."""
        if self._last_result is None:
            self._set_status("No backtest results to export.", error=True)
            return

        try:
            filepath = self.export_service.export_chart_png(
                self.chart_widget,
                self._last_result,
            )
            self._set_status(f"Chart exported to {filepath}")
            self._open_file_location(filepath)
        except Exception as exc:
            logger.exception("Chart export failed")
            self._set_status(f"Export failed: {exc}", error=True)

    def _export_summary(self) -> None:
        """Export summary as text file."""
        if self._last_result is None:
            self._set_status("No backtest results to export.", error=True)
            return

        try:
            filepath = self.export_service.export_summary(self._last_result)
            self._set_status(f"Summary exported to {filepath}")
            self._open_file_location(filepath)
        except Exception as exc:
            logger.exception("Summary export failed")
            self._set_status(f"Export failed: {exc}", error=True)

    def _export_all(self) -> None:
        """Export both chart and summary."""
        if self._last_result is None:
            self._set_status("No backtest results to export.", error=True)
            return

        try:
            chart_path, summary_path = self.export_service.export_all(
                self.chart_widget,
                self._last_result,
            )
            self._set_status(f"Exported to {self.export_service.output_dir}")
            self._open_file_location(chart_path.parent)
        except Exception as exc:
            logger.exception("Export failed")
            self._set_status(f"Export failed: {exc}", error=True)

    def _open_file_location(self, path) -> None:
        """Open file location in system file browser."""
        import subprocess
        import platform

        try:
            path = str(path)
            if platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", path], check=False)
            elif platform.system() == "Darwin":
                subprocess.run(["open", "-R", path], check=False)
            else:
                subprocess.run(["xdg-open", str(Path(path).parent)], check=False)
        except Exception:
            pass

    def save_layout(self) -> dict:
        """Save current splitter positions for persistence."""
        return {
            "main_splitter": self.main_splitter.sizes(),
            "control_splitter": self.control_splitter.sizes(),
            "collapsed": {
                "params": self.params_panel.is_collapsed(),
                "strategy": self.strategy_panel.is_collapsed(),
                "ensemble": self.ensemble_panel_wrapper.is_collapsed(),
                "actions": self.actions_panel.is_collapsed(),
                "results": self.results_panel_wrapper.is_collapsed(),
            },
        }

    def restore_layout(self, layout: dict) -> None:
        """Restore splitter positions from saved layout."""
        if "main_splitter" in layout:
            self.main_splitter.setSizes(layout["main_splitter"])
        if "control_splitter" in layout:
            self.control_splitter.setSizes(layout["control_splitter"])
        if "collapsed" in layout:
            collapsed = layout["collapsed"]
            if "params" in collapsed:
                self.params_panel.set_collapsed(collapsed["params"])
            if "strategy" in collapsed:
                self.strategy_panel.set_collapsed(collapsed["strategy"])
            if "ensemble" in collapsed:
                self.ensemble_panel_wrapper.set_collapsed(collapsed["ensemble"])
            if "actions" in collapsed:
                self.actions_panel.set_collapsed(collapsed["actions"])
            if "results" in collapsed:
                self.results_panel_wrapper.set_collapsed(collapsed["results"])

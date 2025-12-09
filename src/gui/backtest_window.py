from __future__ import annotations

import logging
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from src.services.backtest_service import BacktestService
from src.services.market_data_service import MarketDataService
from src.strategies import create_strategy, get_available_strategies
from src.gui.backtest_chart import BacktestChartWidget
from src.gui.backtest_results_panel import BacktestResultsPanel
from src.gui.strategy_config_widget import StrategyConfigWidget
from src.gui.strategy_selector import StrategySelectorBar

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

        # Strategy selector bar at top
        self.strategy_selector = StrategySelectorBar()
        self.strategy_selector.strategySelected.connect(self._on_strategy_selected)
        main_layout.addWidget(self.strategy_selector)

        # Content area
        content_layout = QtWidgets.QHBoxLayout()

        # Left side: Charts (2/3 width)
        self.chart_widget = BacktestChartWidget()
        content_layout.addWidget(self.chart_widget, stretch=2)

        # Right side: Controls and results (1/3 width)
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        # Study parameters
        params_group = QtWidgets.QGroupBox("Study Parameters")
        params_layout = QtWidgets.QFormLayout()

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

        params_group.setLayout(params_layout)
        right_layout.addWidget(params_group)

        # Strategy config placeholder
        self._strategy_config_container = QtWidgets.QVBoxLayout()
        right_layout.addLayout(self._strategy_config_container)

        # Run button
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
        right_layout.addWidget(self.btn_run)

        # Status label
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: #888888;")
        right_layout.addWidget(self.lbl_status)

        # Results panel
        self.results_panel = BacktestResultsPanel()
        right_layout.addWidget(self.results_panel)

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addLayout(content_layout)

        # Initialize with first strategy
        strategies = get_available_strategies()
        if strategies:
            self._on_strategy_selected(strategies[0])

    def _on_strategy_selected(self, strategy_name: str) -> None:
        """Handle strategy selection change."""
        self._current_strategy_name = strategy_name

        # Remove old config widget
        if self._strategy_config_widget is not None:
            self._strategy_config_widget.deleteLater()
            self._strategy_config_widget = None

        # Create new config widget for selected strategy
        strategy = create_strategy(strategy_name)
        self._strategy_config_widget = StrategyConfigWidget(strategy)
        self._strategy_config_container.addWidget(self._strategy_config_widget)

        # Clear previous results
        self.chart_widget.clear()
        self.results_panel.clear()
        self._set_status(f"Selected strategy: {strategy.display_name}")

    def _run_backtest(self) -> None:
        """Execute backtest with current parameters."""
        ticker = self.txt_ticker.text().strip().upper()
        if not ticker:
            self._set_status("Please enter a ticker symbol.", error=True)
            return

        if not self._current_strategy_name:
            self._set_status("Please select a strategy.", error=True)
            return

        self._set_status(f"Running {self._current_strategy_name} backtest for {ticker}...")
        self.btn_run.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        try:
            # Gather strategy parameters from config widget
            strategy_params = {}
            if self._strategy_config_widget:
                strategy_params = self._strategy_config_widget.get_parameters()

            # Run backtest
            result = self.backtest_service.run_backtest(
                ticker=ticker,
                strategy_name=self._current_strategy_name,
                days=self.spin_days.value(),
                starting_capital=self.spin_capital.value(),
                commission=self.spin_commission.value(),
                slippage=self.spin_slippage.value() / 100,
                strategy_params=strategy_params,
            )

            # Store for export
            self._last_result = result

            # Get data for plotting
            strategy = create_strategy(self._current_strategy_name, **strategy_params)
            df = self._fetch_data_for_plotting(ticker, self.spin_days.value())
            df = strategy.run(df)
            self._last_df = df

            # Get chart config from strategy
            chart_config = strategy.get_chart_config()

            # Update charts
            self.chart_widget.plot_results(
                result=result,
                price_data=df["Close"].values,
                df=df,
                chart_config=chart_config,
                indicator_name=self._current_strategy_name,
            )

            # Update results panel
            self.results_panel.update_results(result)

            self._set_status(
                f"Backtest complete: {result.total_return:+.2f}% return, "
                f"{result.num_trades} trades",
                error=False,
            )

        except Exception as exc:
            logger.exception("Backtest failed")
            self._set_status(f"Error: {exc}", error=True)

        finally:
            self.btn_run.setEnabled(True)

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

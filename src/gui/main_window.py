from __future__ import annotations

import logging
import threading
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from config import (
    MARK_PRICE_SOURCE,
    LOAD_GUARD_SAFETY_MS,
    SNAPSHOT_REFRESH_SECONDS,
    WS_START_GRACE_MS,
    WS_STOP_WAIT_MS,
    CHART_LOOKBACK_DAYS,
    CHART_INTRADAY_REFRESH_MS,
    CHART_DAILY_REFRESH_MS,
    TAPE_BACKFILL_ENABLED,
)
from src.data_models import CompanyDetails, DailyStats, RollingStats
from src.gui_trade import TradeTab
from src.oms import Broker
from src.polygon_client import PolygonClient
from src.controllers.main_controller import MainController
from src.services.market_data_service import MarketDataService
from src.utils.formatting import _fmt_price, _ts_to_dt_utc
from src.gui.ws_thread import WsThread
from src.gui.info_tab import InfoTab
from src.gui.chart_tab import ChartTab
from src.gui.backtest_window import BacktestWindow


logger = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    price_update = QtCore.pyqtSignal(float, float, object)  # price, prev_close, last_trade_dt
    today_update = QtCore.pyqtSignal(object, object, object, object)  # open, high, low, volume
    keys_update = QtCore.pyqtSignal(object, object, object, object, object, object, str)
    company_update = QtCore.pyqtSignal(str, str)
    ws_status_update = QtCore.pyqtSignal(str)
    chart_candles_ready = QtCore.pyqtSignal(object, object, str)
    chart_set_ticker = QtCore.pyqtSignal(str)

    def __init__(
        self,
        client: PolygonClient,
        market_data: MarketDataService,
        controller: Optional[MainController] = None,
    ):
        super().__init__()

        # Dependency injection with default
        self.controller = controller or MainController(self)

        # Authentication and account setup
        if not self.controller.run_auth_flow():
            sys.exit(1)
        self.active_account = self.controller.initialize_account()
        self.session = self.controller.session
        self.user_id = self.controller.user_id

        self.client = client
        self.market_data = market_data
        self._ws_thread: Optional[WsThread] = None
        self._snapshot_timer = QtCore.QTimer(self)
        self._snapshot_timer.setInterval(SNAPSHOT_REFRESH_SECONDS * 1000)
        self._snapshot_timer.timeout.connect(self._on_snapshot_timer)
        self._loading_in_progress = False
        self._load_guard_timer = QtCore.QTimer(self)
        self._load_guard_timer.setSingleShot(True)
        self._load_guard_timer.timeout.connect(self._clear_loading_flag)

        self._current_ticker: Optional[str] = None
        self._prev_close: Optional[float] = None
        self._last_trade_price: Optional[float] = None
        self._last_trade_time_utc: Optional[datetime] = None
        self._chart_loaded_for_ticker: Optional[str] = None
        self._current_chart_level: str = 'L1'
        self._current_timeframe: Optional[str] = None
        self._chart_timer = QtCore.QTimer(self)
        self._chart_timer.timeout.connect(self._on_chart_refresh_timer)
        self.broker: Optional[Broker] = None
        self.tradeTab: Optional[TradeTab] = None

        self._build_ui()
        self._wire_signals()
        if hasattr(self.tab_info, "tapeWidget"):
            self.tab_info.tapeWidget.setFetchTradesCallback(self.market_data.fetch_trades_today)
        self._setup_trade_components()

    def _build_ui(self) -> None:
        self.setWindowTitle("Stock Data Viewer (Polygon.io - Delayed)")
        central = QtWidgets.QWidget(self)
        v = QtWidgets.QVBoxLayout(central)

        # Top controls
        controls = QtWidgets.QHBoxLayout()
        self.txt_ticker = QtWidgets.QLineEdit()
        self.txt_ticker.setPlaceholderText("Enter ticker, e.g., AAPL")
        self.btn_load = QtWidgets.QPushButton("Load")
        controls.addWidget(self.txt_ticker)
        controls.addWidget(self.btn_load)

        # Status line
        status_layout = QtWidgets.QHBoxLayout()
        self.lbl_ws_indicator = QtWidgets.QLabel("●")
        self.lbl_ws_indicator.setStyleSheet("color: gray;")
        self.lbl_ws_status = QtWidgets.QLabel("Feed status: —")
        self.lbl_last_update = QtWidgets.QLabel("Last Update: —")
        status_layout.addWidget(self.lbl_ws_indicator)
        status_layout.addWidget(self.lbl_ws_status)
        status_layout.addStretch(1)
        status_layout.addWidget(self.lbl_last_update)

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tab_info = InfoTab()
        self.tab_chart = ChartTab()
        self.tab_backtest = BacktestWindow(self.market_data)
        self.tabs.addTab(self.tab_info, "Info")
        self.tabs.addTab(self.tab_chart, "Chart")
        self.tabs.addTab(self.tab_backtest, "Backtest")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        v.addLayout(controls)
        v.addLayout(status_layout)
        v.addWidget(self.tabs)

        self.setCentralWidget(central)

        self.btn_load.clicked.connect(self._on_load_clicked)

    def _wire_signals(self) -> None:
        self.price_update.connect(self.tab_info.set_live)
        self.today_update.connect(self.tab_info.set_today)
        self.keys_update.connect(self.tab_info.set_key_metrics)
        self.company_update.connect(self.tab_info.set_company)
        self.ws_status_update.connect(self._on_ws_status)
        self.chart_candles_ready.connect(self.tab_chart.onCandles)
        self.price_update.connect(self.tab_chart.onPrice)
        self.price_update.connect(self._handle_price_update_for_broker)
        self.ws_status_update.connect(self.tab_chart.onStatus)
        self.chart_set_ticker.connect(self.tab_chart.setTicker)
        # Chart requests (from ChartTab)
        try:
            self.tab_chart.requestCandles.disconnect()
        except Exception:
            pass
        self.tab_chart.requestCandles.connect(self._on_chart_request_level)
        try:
            self.tab_chart.requestTimeframe.disconnect()
        except Exception:
            pass
        self.tab_chart.requestTimeframe.connect(self._on_timeframe_selected)

    def _setup_trade_components(self) -> None:
        try:
            self.broker = Broker(self.active_account, self._mark_price)
        except Exception as exc:
            logger.warning("Broker initialization failed: %s", exc)
            self.broker = None
            return
        self.broker.orderAccepted.connect(self.onOrderAccepted)
        self.broker.orderFilled.connect(self.onOrderFilled)
        self.broker.positionsUpdated.connect(self.onPositionsUpdated)
        self.broker.portfolioUpdated.connect(self.onPortfolioUpdated)
        self.broker.omsError.connect(self.onOmsError)
        self.tradeTab = TradeTab(self.broker, self._mark_price)
        self.tabs.addTab(self.tradeTab, "Trade")
        self.tradeTab.loadTickerRequested.connect(self.onLoadTickerFromTrade)

    # ----------------- Chart refresh helpers -----------------
    @QtCore.pyqtSlot()
    def _on_chart_refresh_timer(self) -> None:
        if not self._current_ticker:
            return
        if self._current_timeframe:
            # Refresh current timeframe window
            try:
                self._fetch_timeframe(self._current_timeframe)
            except Exception:
                pass
        else:
            # Refresh current zoom-driven level
            try:
                self._on_chart_request_level(self._current_chart_level)
            except Exception:
                pass

    @QtCore.pyqtSlot()
    def _restart_chart_timer(self) -> None:
        if self._current_timeframe:
            self._set_chart_timer_interval_by_timeframe(self._current_timeframe)
        else:
            self._set_chart_timer_interval_by_level(self._current_chart_level)

    def _set_chart_timer_interval_by_timeframe(self, tf: str) -> None:
        # Faster for intraday, slower for daily
        if tf in ('1D', '1W'):
            self._chart_timer.start(CHART_INTRADAY_REFRESH_MS)
        else:
            self._chart_timer.start(CHART_DAILY_REFRESH_MS)

    def _set_chart_timer_interval_by_level(self, level: str) -> None:
        if level in ('L3', 'L4', 'L5'):
            self._chart_timer.start(CHART_INTRADAY_REFRESH_MS)
        else:
            self._chart_timer.start(CHART_DAILY_REFRESH_MS)

    @QtCore.pyqtSlot()
    def _start_snapshot_timer(self) -> None:
        try:
            self._snapshot_timer.start()
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def _schedule_start_ws(self) -> None:
        QtCore.QTimer.singleShot(WS_START_GRACE_MS, self._start_ws)

    @QtCore.pyqtSlot(str)
    def _on_timeframe_selected(self, tf: str) -> None:
        if not self._current_ticker:
            return
        self._current_timeframe = tf
        level_label = {
            '1D': '5m',
            '1W': '30m',
            '1M': '1D',
            '3M': '1D',
            'YTD': '1D',
            '1Y': '1D',
            '5Y': '1D',
        }.get(tf, '1D')
        self.tab_chart.setRangeLabel(f"{tf} ({level_label})")
        self.tab_chart.setTimeframeSelection(tf)
        # Lock chart view within timeframe window
        self.tab_chart.setViewLock(True)
        self._fetch_timeframe(tf)
        self._set_chart_timer_interval_by_timeframe(tf)

    def _fetch_timeframe(self, tf: str) -> None:
        ticker = self._current_ticker
        def _fetch():
            try:
                now = datetime.now(timezone.utc)
                if tf == '1D':
                    start = now - timedelta(days=1)
                    data = self.market_data.get_aggs_range(ticker, 5, 'minute', start.date().isoformat(), now.date().isoformat())
                    level = 'L4'
                elif tf == '1W':
                    start = now - timedelta(days=7)
                    data = self.market_data.get_aggs_range(ticker, 30, 'minute', start.date().isoformat(), now.date().isoformat())
                    level = 'L3'
                elif tf == '1M':
                    start = now - timedelta(days=30)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == '3M':
                    start = now - timedelta(days=90)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == 'YTD':
                    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == '5Y':
                    start = now - timedelta(days=365*5)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L1'
                else:  # '1Y'
                    start = now - timedelta(days=365)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L1'

                results = data.get('results') or []
                if not results:
                    return
                arr = np.zeros((len(results), 7), dtype=float)
                dt_list = []
                for i, r in enumerate(results):
                    t_ms = float(r.get('t', 0))
                    t_sec = t_ms / 1000.0
                    o = float(r.get('o', np.nan))
                    h = float(r.get('h', np.nan))
                    l = float(r.get('l', np.nan))
                    c = float(r.get('c', np.nan))
                    v = float(r.get('v', 0.0))
                    arr[i, 0] = t_sec
                    arr[i, 1] = o
                    arr[i, 2] = h
                    arr[i, 3] = l
                    arr[i, 4] = c
                    arr[i, 5] = v
                    arr[i, 6] = 1.0 if c >= o else 0.0
                    dt_list.append(datetime.fromtimestamp(t_sec, tz=timezone.utc))
                self._current_chart_level = level
                self.chart_candles_ready.emit(arr, dt_list, level)
            except Exception as exc:
                logger.debug('Timeframe fetch failed for %s %s: %s', ticker, tf, exc)
        threading.Thread(target=_fetch, daemon=True).start()

    

    # ----------------- Event handlers -----------------
    def _on_tab_changed(self, idx: int) -> None:
        if idx == 1 and self._current_ticker and self._chart_loaded_for_ticker != self._current_ticker:
            # Lazy-load chart
            threading.Thread(target=self._load_chart_data, args=(self._current_ticker,), daemon=True).start()

    def _on_ws_status(self, status: str) -> None:
        self.lbl_ws_status.setText(f"Feed status: {status}")
        color = {
            "CONNECTING": "#888888",
            "CONNECTED": "#1f77b4",
            "DELAYED": "#ff7f0e",
            "RECONNECTING": "#bcbd22",
            "ERROR": "#d62728",
            "DISCONNECTED": "#888888",
        }.get(status, "gray")
        self.lbl_ws_indicator.setStyleSheet(f"color: {color};")

    def _on_snapshot_timer(self) -> None:
        if not self._current_ticker or self._loading_in_progress:
            return
        threading.Thread(target=self._do_snapshot_update, args=(self._current_ticker,), daemon=True).start()

    def _on_load_clicked(self) -> None:
        ticker = (self.txt_ticker.text() or "").strip().upper()
        if not ticker:
            return
        if self._loading_in_progress:
            return
        self._loading_in_progress = True
        self.btn_load.setEnabled(False)
        self._load_guard_timer.start(LOAD_GUARD_SAFETY_MS)

        # Stop old WS + snapshot timer
        self._stop_ws()
        self._snapshot_timer.stop()
        self._chart_timer.stop()

        # Start load in background
        threading.Thread(target=self._load_ticker, args=(ticker,), daemon=True).start()

    @QtCore.pyqtSlot()
    def _clear_loading_flag(self) -> None:
        self._loading_in_progress = False
        self.btn_load.setEnabled(True)

    # ----------------- Data loading -----------------
    def _load_ticker(self, ticker: str) -> None:
        try:
            # Collect REST data
            details = self.market_data.get_ticker_details(ticker)
            prev = self.market_data.get_previous_close(ticker)
            snap = self.market_data.get_snapshot(ticker)

            # Derive daily stats and rolling metrics
            prev_close = None
            if prev.get("results"):
                prev_close = prev["results"][0].get("c")

            last_trade_price = None
            last_trade_time = None
            open_p = None
            high = None
            low = None
            volume = None

            ticker_json = (snap or {}).get("ticker") or {}
            lastTrade = ticker_json.get("lastTrade") or {}
            day = ticker_json.get("day") or {}
            if lastTrade:
                last_trade_price = lastTrade.get("p")
                last_trade_time = _ts_to_dt_utc(lastTrade.get("t", 0))
            if day:
                open_p = day.get("o")
                high = day.get("h")
                low = day.get("l")
                volume = day.get("v")

            name = None
            description = None
            market_cap = None
            pe_ratio = None
            res = details.get("results") or {}
            if res:
                name = res.get("name")
                description = res.get("description")
                market_cap = res.get("market_cap")
                pe_ratio = res.get("share_class_shares_outstanding") and None  # placeholder if not provided
                # Polygon v3 reference does not always provide PE ratio; leave None if absent

            # Rolling stats
            end = datetime.now(timezone.utc)
            start_30 = end - timedelta(days=35)
            start_365 = end - timedelta(days=CHART_LOOKBACK_DAYS + 10)
            agg_30 = self.market_data.get_daily_aggs_range(ticker, start_30.date().isoformat(), end.date().isoformat())
            agg_365 = self.market_data.get_daily_aggs_range(ticker, start_365.date().isoformat(), end.date().isoformat())

            vols = [(r.get("v") or 0) for r in (agg_30.get("results") or [])[-30:]]
            avg_vol_30d = float(np.mean(vols)) if vols else None
            prices = [
                (float(r.get("h")), float(r.get("l")))
                for r in (agg_365.get("results") or [])
                if r.get("h") is not None and r.get("l") is not None
            ]
            w52h = max([p[0] for p in prices]) if prices else None
            w52l = min([p[1] for p in prices]) if prices else None

            market_status = MarketDataService.get_market_status()

            # Emit to UI
            self._current_ticker = ticker
            self._prev_close = float(prev_close) if prev_close is not None else None
            self._last_trade_price = float(last_trade_price) if last_trade_price is not None else None
            self._last_trade_time_utc = last_trade_time

            self.company_update.emit(name or ticker, description or "")
            self.today_update.emit(open_p, high, low, volume)
            self.keys_update.emit(self._prev_close, avg_vol_30d, w52h, w52l, market_cap, pe_ratio, market_status)
            self.price_update.emit(self._last_trade_price or 0.0, self._prev_close or 0.0, self._last_trade_time_utc)
            QtCore.QMetaObject.invokeMethod(self, "_set_last_update_now", QtCore.Qt.QueuedConnection)
            QtCore.QMetaObject.invokeMethod(
                self,
                "_load_tape_for_ticker",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, ticker),
            )
            # Notify chart of current ticker (for cache key semantics if needed)
            self.chart_set_ticker.emit(ticker)

            # Start snapshot poller and websocket after a small grace delay (in GUI thread)
            QtCore.QMetaObject.invokeMethod(self, "_schedule_start_ws", QtCore.Qt.QueuedConnection)
            QtCore.QMetaObject.invokeMethod(self, "_start_snapshot_timer", QtCore.Qt.QueuedConnection)
        except Exception as exc:
            logger.exception("Failed to load ticker %s: %s", ticker, exc)
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Failed to load ticker {ticker}: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(self, "_clear_loading_flag", QtCore.Qt.QueuedConnection)

    def _load_chart_data(self, ticker: str) -> None:
        try:
            end = datetime.now(timezone.utc).date()
            start = (datetime.now(timezone.utc) - timedelta(days=CHART_LOOKBACK_DAYS)).date()
            data = self.market_data.get_daily_aggs_range(ticker, start.isoformat(), end.isoformat())
            results = data.get("results") or []
            if not results:
                return
            # Build array: [t_utc, open, high, low, close, volume, is_up]
            arr = np.zeros((len(results), 7), dtype=float)
            dt_list = []
            for i, r in enumerate(results):
                t_ms = float(r.get("t", 0))
                t_sec = t_ms / 1000.0
                o = float(r.get("o", np.nan))
                h = float(r.get("h", np.nan))
                l = float(r.get("l", np.nan))
                c = float(r.get("c", np.nan))
                v = float(r.get("v", 0.0))
                arr[i, 0] = t_sec
                arr[i, 1] = o
                arr[i, 2] = h
                arr[i, 3] = l
                arr[i, 4] = c
                arr[i, 5] = v
                arr[i, 6] = 1.0 if c >= o else 0.0
                dt_list.append(datetime.fromtimestamp(t_sec, tz=timezone.utc))
            self._chart_loaded_for_ticker = ticker
            # Level L1 for ~1Y view
            self.chart_candles_ready.emit(arr, dt_list, 'L1')
            # Set default timeframe and start refresh timer
            self._current_chart_level = 'L1'
            self._current_timeframe = '1Y'
            QtCore.QMetaObject.invokeMethod(self, "_restart_chart_timer", QtCore.Qt.QueuedConnection)
            QtCore.QMetaObject.invokeMethod(self.tab_chart, "setTimeframeSelection", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, '1Y'))
            QtCore.QMetaObject.invokeMethod(self.tab_chart, "setRangeLabel", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, '1Y (1D)'))
            QtCore.QMetaObject.invokeMethod(self.tab_chart, "setViewLock", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(bool, True))
        except Exception as exc:
            logger.warning("Failed to load chart candles for %s: %s", ticker, exc)


    @QtCore.pyqtSlot(str)
    def _on_chart_request_level(self, level: str) -> None:
        # Fetch appropriate aggregation for current ticker and send to chart
        if not self._current_ticker:
            return
        ticker = self._current_ticker
        self._current_chart_level = level
        self._current_timeframe = None  # level-driven view supersedes fixed timeframe
        self._set_chart_timer_interval_by_level(level)
        def _fetch():
            try:
                end_dt = datetime.now(timezone.utc)
                # choose start by level
                if level in ('L1', 'L2'):
                    start_dt = end_dt - timedelta(days=CHART_LOOKBACK_DAYS)
                    data = self.market_data.get_aggs_range(ticker, 1, 'day', start_dt.date().isoformat(), end_dt.date().isoformat())
                elif level == 'L3':
                    start_dt = end_dt - timedelta(days=30)
                    try:
                        data = self.market_data.get_aggs_range(ticker, 30, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.market_data.get_aggs_range(ticker, 1, 'day', start_dt.date().isoformat(), end_dt.date().isoformat())
                elif level == 'L4':
                    start_dt = end_dt - timedelta(days=3)
                    try:
                        data = self.market_data.get_aggs_range(ticker, 5, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.market_data.get_aggs_range(ticker, 15, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                else:  # L5
                    start_dt = end_dt - timedelta(days=1)
                    try:
                        data = self.market_data.get_aggs_range(ticker, 1, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.market_data.get_aggs_range(ticker, 5, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())

                results = data.get('results') or []
                if not results:
                    return
                arr = np.zeros((len(results), 7), dtype=float)
                dt_list = []
                for i, r in enumerate(results):
                    t_ms = float(r.get('t', 0))
                    t_sec = t_ms / 1000.0
                    o = float(r.get('o', np.nan))
                    h = float(r.get('h', np.nan))
                    l = float(r.get('l', np.nan))
                    c = float(r.get('c', np.nan))
                    v = float(r.get('v', 0.0))
                    arr[i, 0] = t_sec
                    arr[i, 1] = o
                    arr[i, 2] = h
                    arr[i, 3] = l
                    arr[i, 4] = c
                    arr[i, 5] = v
                    arr[i, 6] = 1.0 if c >= o else 0.0
                    dt_list.append(datetime.fromtimestamp(t_sec, tz=timezone.utc))
                self.chart_candles_ready.emit(arr, dt_list, level)
            except Exception as exc:
                logger.debug('Level fetch failed for %s %s: %s', ticker, level, exc)
        threading.Thread(target=_fetch, daemon=True).start()

    def _do_snapshot_update(self, ticker: str) -> None:
        try:
            snap = self.market_data.get_snapshot(ticker)
            ticker_json = (snap or {}).get("ticker") or {}
            lastTrade = ticker_json.get("lastTrade") or {}
            if lastTrade:
                self._last_trade_price = lastTrade.get("p")
                self._last_trade_time_utc = _ts_to_dt_utc(lastTrade.get("t", 0))

            if self._last_trade_price is not None:
                self.price_update.emit(self._last_trade_price, self._prev_close or 0.0, self._last_trade_time_utc)
                QtCore.QMetaObject.invokeMethod(self, "_set_last_update_now", QtCore.Qt.QueuedConnection)
        except Exception as exc:
            logger.debug("Snapshot update failed: %s", exc)

    @QtCore.pyqtSlot(str)
    def _load_tape_for_ticker(self, ticker: str) -> None:
        if not ticker or not hasattr(self.tab_info, "tapeWidget"):
            return
        if not TAPE_BACKFILL_ENABLED:
            return
        try:
            self.tab_info.tapeWidget.loadTicker(ticker)
        except Exception as exc:
            logger.debug("Tape widget load failed: %s", exc)

    # ----------------- WebSocket lifecycle -----------------
    def _start_ws(self) -> None:
        if not self._current_ticker:
            return
        # Ensure no existing thread
        self._stop_ws()
        self._ws_thread = WsThread(self.client, self._current_ticker)
        self._ws_thread.trade_signal.connect(self._on_trade_event)
        self._ws_thread.status_signal.connect(self.ws_status_update)
        self._ws_thread.start()

    def _stop_ws(self) -> None:
        if self._ws_thread is None:
            return
        try:
            self._ws_thread.status_signal.disconnect()
        except Exception:
            pass
        try:
            self._ws_thread.trade_signal.disconnect()
        except Exception:
            pass
        try:
            self._ws_thread.requestInterruption()
            self._ws_thread.stop()
            self._ws_thread.quit()
            finished = self._ws_thread.wait(WS_STOP_WAIT_MS)
            if not finished:
                # Give it extra time to tear down the asyncio loop and WS
                finished = self._ws_thread.wait(3000)
            if not finished:
                # Last resort to avoid crash on GC; termination is unsafe but prevents hard close
                try:
                    self._ws_thread.terminate()
                except Exception:
                    pass
                self._ws_thread.wait(1000)
        finally:
            try:
                self._ws_thread.deleteLater()
            except Exception:
                pass
            self._ws_thread = None

    def _on_trade_event(self, ev: Dict[str, Any]) -> None:
        # Polygon trade event fields: p=price, t=timestamp, etc.
        price = ev.get("p")
        ts = ev.get("t")
        if price is not None:
            self._last_trade_price = float(price)
        if ts:
            self._last_trade_time_utc = _ts_to_dt_utc(ts)
        if self._last_trade_price is not None:
            self.price_update.emit(self._last_trade_price, self._prev_close or 0.0, self._last_trade_time_utc)
            self._set_last_update_now()
            if hasattr(self.tab_info, "tapeWidget"):
                try:
                    self.tab_info.tapeWidget.appendTrade(ev)
                except Exception as exc:
                    logger.debug("Tape append error: %s", exc)

    @QtCore.pyqtSlot(float, float, object)
    def _handle_price_update_for_broker(self, price: float, prev_close: float, last_trade: object) -> None:  # noqa: ARG002
        if not self.broker:
            return
        try:
            self.broker.refresh_portfolio()
        except Exception as exc:
            logger.debug("Broker refresh failed: %s", exc)

    # ----------------- UI helpers -----------------
    @QtCore.pyqtSlot(str)
    def _show_error(self, msg: str) -> None:
        QtWidgets.QMessageBox.warning(self, "Load Error", msg)

    @QtCore.pyqtSlot()
    def _set_last_update_now(self) -> None:
        now_utc = datetime.now(timezone.utc)
        self.lbl_last_update.setText(f"Last Update: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # ----------------- Qt overrides -----------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self.controller.shutdown()
        try:
            self._snapshot_timer.stop()
            self._chart_timer.stop()
            self._stop_ws()
        finally:
            super().closeEvent(event)

    # === PHASE 2 additions ===
    def _mark_price(self, ticker: str) -> float:
        if self._last_trade_price:
            return float(self._last_trade_price)
        return 0.0

    @QtCore.pyqtSlot(str)
    def onOrderAccepted(self, order_id: str) -> None:
        if self.tradeTab:
            self.tradeTab.onOrderAccepted(order_id)

    @QtCore.pyqtSlot(object)
    def onOrderFilled(self, fill: object) -> None:
        if self.tradeTab:
            self.tradeTab.onOrderFilled(fill)

    @QtCore.pyqtSlot(list)
    def onPositionsUpdated(self, positions) -> None:
        if self.tradeTab:
            self.tradeTab.updatePositions(positions)

    @QtCore.pyqtSlot(dict)
    def onPortfolioUpdated(self, portfolio) -> None:
        if self.tradeTab:
            self.tradeTab.updatePortfolio(portfolio)

    @QtCore.pyqtSlot(str)
    def onLoadTickerFromTrade(self, ticker: str) -> None:
        if not ticker:
            return
        self.txt_ticker.setText(ticker)
        self._on_load_clicked()

    @QtCore.pyqtSlot(str)
    def onOmsError(self, error_msg: str) -> None:
        QtWidgets.QMessageBox.warning(self, "Order Error", error_msg)

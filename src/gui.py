from __future__ import annotations

import asyncio
import logging
import threading
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from dateutil import tz
from PyQt5 import QtCore, QtGui, QtWidgets

from config import (
    STARTING_CAPITAL,
    MARK_PRICE_SOURCE,
    LOAD_GUARD_SAFETY_MS,
    SNAPSHOT_REFRESH_SECONDS,
    WS_START_GRACE_MS,
    WS_STOP_WAIT_MS,
    CHART_LOOKBACK_DAYS,
    CHART_INTRADAY_REFRESH_MS,
    CHART_DAILY_REFRESH_MS,
    TAPE_BACKFILL_ENABLED,
    CHART_TRANSITION_ENABLED,
    CHART_TRANSITION_DURATION_MS,
    CHART_ZOOM_ANIMATION_DURATION_MS,
)
from src.auth_client import sign_out
from src.data_models import CompanyDetails, DailyStats, RollingStats
from src.gui_auth import AuthDialog
from src.gui_tape import TapeWidget
from src.gui_trade import TradeTab
from src.oms import Broker
from src.polygon_client import PolygonClient
from src.supabase_store import (
    SupabaseStoreError,
    create_default_account,
    ensure_schema,
    load_accounts,
)


logger = logging.getLogger(__name__)


class WsThread(QtCore.QThread):
    trade_signal = QtCore.pyqtSignal(dict)
    status_signal = QtCore.pyqtSignal(str)

    def __init__(self, client: PolygonClient, ticker: str, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.client = client
        self.ticker = ticker
        self._stop_event: Optional[asyncio.Event] = None

    def run(self) -> None:  # noqa: D401
        """Run an asyncio loop for the WebSocket stream."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._stop_event = asyncio.Event()

        async def _runner():
            await self.client.stream_ticker(
                ticker=self.ticker,
                on_data=self.trade_signal.emit,
                on_status=self.status_signal.emit,
                stop_event=self._stop_event,
            )

        try:
            loop.run_until_complete(_runner())
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.stop()
            loop.close()

    def stop(self) -> None:
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()


class InfoTab(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.layout = QtWidgets.QVBoxLayout(self)

        # Live Data Section
        live_group = QtWidgets.QGroupBox("Live Data")
        grid_live = QtWidgets.QGridLayout()
        self.lbl_price = QtWidgets.QLabel("—")
        self.lbl_change_d = QtWidgets.QLabel("—")
        self.lbl_change_p = QtWidgets.QLabel("—")
        self.lbl_last_trade = QtWidgets.QLabel("—")
        grid_live.addWidget(QtWidgets.QLabel("Price"), 0, 0)
        grid_live.addWidget(self.lbl_price, 0, 1)
        grid_live.addWidget(QtWidgets.QLabel("Change ($)"), 0, 2)
        grid_live.addWidget(self.lbl_change_d, 0, 3)
        grid_live.addWidget(QtWidgets.QLabel("Change (%)"), 0, 4)
        grid_live.addWidget(self.lbl_change_p, 0, 5)
        grid_live.addWidget(QtWidgets.QLabel("Last Trade"), 1, 0)
        grid_live.addWidget(self.lbl_last_trade, 1, 1, 1, 5)
        live_group.setLayout(grid_live)

        # Today's Stats
        stats_group = QtWidgets.QGroupBox("Today's Stats")
        grid_stats = QtWidgets.QGridLayout()
        self.lbl_open = QtWidgets.QLabel("—")
        self.lbl_high = QtWidgets.QLabel("—")
        self.lbl_low = QtWidgets.QLabel("—")
        self.lbl_volume = QtWidgets.QLabel("—")
        grid_stats.addWidget(QtWidgets.QLabel("Open"), 0, 0)
        grid_stats.addWidget(self.lbl_open, 0, 1)
        grid_stats.addWidget(QtWidgets.QLabel("High"), 0, 2)
        grid_stats.addWidget(self.lbl_high, 0, 3)
        grid_stats.addWidget(QtWidgets.QLabel("Low"), 1, 0)
        grid_stats.addWidget(self.lbl_low, 1, 1)
        grid_stats.addWidget(QtWidgets.QLabel("Volume"), 1, 2)
        grid_stats.addWidget(self.lbl_volume, 1, 3)
        stats_group.setLayout(grid_stats)

        # Key Metrics
        key_group = QtWidgets.QGroupBox("Key Metrics")
        grid_key = QtWidgets.QGridLayout()
        self.lbl_prev_close = QtWidgets.QLabel("—")
        self.lbl_avg_vol_30d = QtWidgets.QLabel("—")
        self.lbl_52w_high = QtWidgets.QLabel("—")
        self.lbl_52w_low = QtWidgets.QLabel("—")
        self.lbl_market_cap = QtWidgets.QLabel("—")
        self.lbl_pe = QtWidgets.QLabel("—")
        self.lbl_market_status = QtWidgets.QLabel("—")
        grid_key.addWidget(QtWidgets.QLabel("Prev Close"), 0, 0)
        grid_key.addWidget(self.lbl_prev_close, 0, 1)
        grid_key.addWidget(QtWidgets.QLabel("Avg Vol (30d)"), 0, 2)
        grid_key.addWidget(self.lbl_avg_vol_30d, 0, 3)
        grid_key.addWidget(QtWidgets.QLabel("52W High"), 1, 0)
        grid_key.addWidget(self.lbl_52w_high, 1, 1)
        grid_key.addWidget(QtWidgets.QLabel("52W Low"), 1, 2)
        grid_key.addWidget(self.lbl_52w_low, 1, 3)
        grid_key.addWidget(QtWidgets.QLabel("Market Cap"), 2, 0)
        grid_key.addWidget(self.lbl_market_cap, 2, 1)
        grid_key.addWidget(QtWidgets.QLabel("P/E Ratio"), 2, 2)
        grid_key.addWidget(self.lbl_pe, 2, 3)
        grid_key.addWidget(QtWidgets.QLabel("Market Status"), 3, 0)
        grid_key.addWidget(self.lbl_market_status, 3, 1, 1, 3)
        key_group.setLayout(grid_key)

        # Company Description
        desc_group = QtWidgets.QGroupBox("Company")
        v_desc = QtWidgets.QVBoxLayout()
        self.lbl_company_name = QtWidgets.QLabel("—")
        self.txt_description = QtWidgets.QTextEdit()
        self.txt_description.setReadOnly(True)
        self.txt_description.setFixedHeight(120)
        v_desc.addWidget(self.lbl_company_name)
        v_desc.addWidget(self.txt_description)
        desc_group.setLayout(v_desc)

        self.layout.addWidget(live_group)
        self.layout.addWidget(stats_group)
        self.layout.addWidget(key_group)
        self.layout.addWidget(desc_group)
        self.tapeWidget = TapeWidget()
        self.layout.addWidget(self.tapeWidget)
        self.layout.addStretch(1)

    # ----- Update helpers -----
    def set_live(self, price: Optional[float], prev_close: Optional[float], last_trade_dt: Optional[datetime]) -> None:
        self.lbl_price.setText(_fmt_price(price))
        if price is not None and prev_close:
            ch = price - prev_close
            pct = (ch / prev_close) * 100.0
        else:
            ch, pct = None, None
        _set_color_number(self.lbl_price, price, prev_close)
        self.lbl_change_d.setText(_fmt_price(ch))
        _set_color_number(self.lbl_change_d, ch, 0)
        self.lbl_change_p.setText(_fmt_pct(pct))
        _set_color_number(self.lbl_change_p, pct, 0)
        self.lbl_last_trade.setText(_fmt_dt_et(last_trade_dt))

    def set_today(self, open_p: Optional[float], high: Optional[float], low: Optional[float], volume: Optional[int]) -> None:
        self.lbl_open.setText(_fmt_price(open_p))
        self.lbl_high.setText(_fmt_price(high))
        self.lbl_low.setText(_fmt_price(low))
        self.lbl_volume.setText(_fmt_int(volume))

    def set_key_metrics(
        self,
        prev_close: Optional[float],
        avg_vol_30d: Optional[float],
        w52h: Optional[float],
        w52l: Optional[float],
        market_cap: Optional[float],
        pe_ratio: Optional[float],
        market_status: str,
    ) -> None:
        self.lbl_prev_close.setText(_fmt_price(prev_close))
        self.lbl_avg_vol_30d.setText(_fmt_int(avg_vol_30d))
        self.lbl_52w_high.setText(_fmt_price(w52h))
        self.lbl_52w_low.setText(_fmt_price(w52l))
        self.lbl_market_cap.setText(_fmt_int(market_cap))
        self.lbl_pe.setText("—" if pe_ratio is None else f"{pe_ratio:.2f}")
        self.lbl_market_status.setText(market_status)

    def set_company(self, name: Optional[str], description: Optional[str]) -> None:
        self.lbl_company_name.setText(name or "—")
        self.txt_description.setPlainText(description or "—")


class ChartTab(QtWidgets.QWidget):
    # ChartTab asks controller (MainWindow) for new candle level
    requestCandles = QtCore.pyqtSignal(str)
    requestTimeframe = QtCore.pyqtSignal(str)
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._built = False
        self._pricePlot: Optional[pg.PlotWidget] = None
        self._volPlot: Optional[pg.PlotWidget] = None
        self._candles: Optional[np.ndarray] = None  # Nx7: t, o,h,l,c,v,is_up
        self._datetimes: Optional[list] = None  # list[datetime]
        self._x_idx: Optional[np.ndarray] = None
        self._up_mask: Optional[np.ndarray] = None
        self._dn_mask: Optional[np.ndarray] = None
        self._wickItem: Optional[pg.ErrorBarItem] = None
        self._bodyUp: Optional[pg.BarGraphItem] = None
        self._bodyDn: Optional[pg.BarGraphItem] = None
        self._volUp: Optional[pg.BarGraphItem] = None
        self._volDn: Optional[pg.BarGraphItem] = None
        # RSI elements
        self._rsiPlot: Optional[pg.PlotWidget] = None
        self._rsiCurve: Optional[pg.PlotDataItem] = None
        self._rsiBand: Optional[pg.LinearRegionItem] = None
        self._rsiVisible: bool = False
        self._current_level: str = 'L1'
        self._current_timeframe: str = '1Y'
        self._level_cache: dict = {}
        self._ticker: Optional[str] = None
        self._vline: Optional[pg.InfiniteLine] = None
        self._hline: Optional[pg.InfiniteLine] = None
        self._priceLine: Optional[pg.InfiniteLine] = None
        self._priceLabel: Optional[pg.TextItem] = None
        self._showVolume: bool = True
        self._logEnabled: bool = False
        self._lock_view: bool = False
        self._range_timer = QtCore.QTimer(self)
        self._range_timer.setSingleShot(True)
        self._range_timer.setInterval(180)
        self._range_timer.timeout.connect(self._emit_range_level)
        self._viewbox: Optional[pg.ViewBox] = None
        self._transitions_enabled: bool = CHART_TRANSITION_ENABLED
        self._fade_duration_ms: int = max(1, CHART_TRANSITION_DURATION_MS // 2)
        self._zoom_animation_ms: int = CHART_ZOOM_ANIMATION_DURATION_MS
        self._fade_overlay = QtWidgets.QWidget(self)
        self._fade_overlay.setStyleSheet("background-color: #111111;")
        self._fade_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self._fade_overlay.hide()
        self._fade_overlay_effect = QtWidgets.QGraphicsOpacityEffect(self._fade_overlay)
        self._fade_overlay_effect.setOpacity(0.0)
        self._fade_overlay.setGraphicsEffect(self._fade_overlay_effect)
        self._fade_animation = QtCore.QPropertyAnimation(self._fade_overlay_effect, b"opacity", self)
        self._fade_animation.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self._fade_animation.finished.connect(self._on_fade_finished)
        self._fade_phase: str = "idle"
        self._pending_transition_callback: Optional[Callable[[], None]] = None
        self._awaiting_data_fade: bool = False
        self._panning_active: bool = False
        self._pan_start_pos: Optional[QtCore.QPoint] = None
        self._pan_start_range: Optional[List[List[float]]] = None
        self._pan_start_view: Optional[QtCore.QPointF] = None
        self._pan_sensitivity: float = 0.2  # lower = less responsive pan
        self._data_time_min: Optional[float] = None
        self._data_time_max: Optional[float] = None
        self._data_time_span: Optional[float] = None
        self._current_bar_interval: float = 1.0
        self._min_visible_bars: float = 10.0
        self._zoom_timer: Optional[QtCore.QTimer] = None
        self._zoom_steps: int = 0
        self._zoom_index: int = 0
        self._zoom_start_range: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
        self._zoom_target_range: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
        self._build_ui()

    def _build_ui(self) -> None:
        pg.setConfigOptions(antialias=True)
        pg.setConfigOptions(useOpenGL=False)
        pg.setConfigOption('background', 'k')
        pg.setConfigOption('foreground', 'w')

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Top bar
        top = QtWidgets.QHBoxLayout()
        self.lbl_range = QtWidgets.QLabel("1Y (1D)")
        self.chk_log = QtWidgets.QCheckBox("Log Y")
        self.chk_vol = QtWidgets.QCheckBox("Volume")
        self.chk_vol.setChecked(True)
        self.chk_rsi = QtWidgets.QCheckBox("RSI")
        self.chk_rsi.setToolTip("Relative Strength Index (14)")
        # Timeframe buttons
        self._tf_buttons: Dict[str, QtWidgets.QPushButton] = {}
        tf_bar = QtWidgets.QHBoxLayout()
        for tf in ["1D", "1W", "1M", "3M", "YTD", "1Y", "5Y"]:
            btn = QtWidgets.QPushButton(tf)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tf: self._on_tf_clicked(t))
            self._tf_buttons[tf] = btn
            tf_bar.addWidget(btn)
        self._tf_buttons["1Y"].setChecked(True)

        top.addWidget(self.lbl_range)
        top.addLayout(tf_bar)
        top.addStretch(1)
        top.addWidget(self.chk_log)
        top.addWidget(self.chk_vol)
        top.addWidget(self.chk_rsi)
        layout.addLayout(top)

        # Plots
        self._pricePlot = pg.PlotWidget()
        self._pricePlot.showGrid(x=False, y=False)
        self._pricePlot.getPlotItem().setMenuEnabled(False)
        self._pricePlot.getPlotItem().hideAxis('left')
        self._pricePlot.getPlotItem().showAxis('right')
        self._pricePlot.setClipToView(True)
        self._volPlot = pg.PlotWidget()
        self._volPlot.setMaximumHeight(180)
        self._volPlot.getPlotItem().hideAxis('left')
        self._volPlot.getPlotItem().showAxis('right')
        self._volPlot.showGrid(x=False, y=False)
        self._volPlot.setClipToView(True)
        # RSI plot (hidden by default)
        self._rsiPlot = pg.PlotWidget()
        self._rsiPlot.setMaximumHeight(160)
        self._rsiPlot.getPlotItem().hideAxis('left')
        self._rsiPlot.getPlotItem().showAxis('right')
        self._rsiPlot.showGrid(x=False, y=False)
        self._rsiPlot.setClipToView(True)
        self._rsiPlot.setVisible(False)

        self._viewbox = self._pricePlot.getPlotItem().getViewBox()
        if self._viewbox:
            self._viewbox.setMouseEnabled(x=False, y=False)
        viewport = self._pricePlot.viewport()
        if viewport is not None:
            viewport.installEventFilter(self)
            viewport.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CrossCursor)

        self._plots_container = QtWidgets.QWidget(self)
        plots_layout = QtWidgets.QVBoxLayout(self._plots_container)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.setSpacing(4)
        plots_layout.addWidget(self._pricePlot)
        plots_layout.addWidget(self._volPlot)
        plots_layout.addWidget(self._rsiPlot)
        layout.addWidget(self._plots_container)
        self._fade_overlay.setParent(self._plots_container)
        self._fade_overlay.setGeometry(self._plots_container.rect())

        # Link X axes
        self._volPlot.setXLink(self._pricePlot)
        self._rsiPlot.setXLink(self._pricePlot)

        # Crosshair
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#9E9E9E66'))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#9E9E9E66'))
        self._pricePlot.addItem(self._vline, ignoreBounds=True)
        self._pricePlot.addItem(self._hline, ignoreBounds=True)

        # Status row
        status_row = QtWidgets.QHBoxLayout()
        self.lbl_cursor = QtWidgets.QLabel("—")
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.lbl_cursor.setFont(f)
        self.lbl_rsi_value = QtWidgets.QLabel("")
        status_row.addWidget(self.lbl_cursor)
        status_row.addStretch(1)
        status_row.addWidget(QtWidgets.QLabel("RSI:"))
        status_row.addWidget(self.lbl_rsi_value)
        layout.addLayout(status_row)

        # Events
        self._pricePlot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.chk_vol.toggled.connect(self.setVolumeVisible)
        self.chk_log.toggled.connect(self.setLogEnabled)
        self.chk_rsi.toggled.connect(self.onToggleRSI)
        # Range change hook for timescale manager
        self._pricePlot.getPlotItem().sigRangeChanged.connect(self._on_range_changed)
        # Keep focus for key shortcuts
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    @QtCore.pyqtSlot(object, object)
    def loadCandles(self, candles: np.ndarray, dts: list) -> None:
        self._candles = candles
        self._datetimes = dts
        n = len(candles)
        self._x_idx = np.arange(n, dtype=float)
        self._up_mask = candles[:, 6] >= 0.5
        self._dn_mask = ~self._up_mask
        self.renderCandles(candles, dts)

    @QtCore.pyqtSlot(object, object, str)
    def onCandles(self, candles: np.ndarray, dts: list, level: str) -> None:
        self._current_level = level
        self._current_bar_interval = self._bar_interval_for_level(level)
        self.loadCandles(candles, dts)

    @QtCore.pyqtSlot(str)
    def setTicker(self, ticker: str) -> None:
        self._ticker = ticker
        # reset level to default on new ticker
        self._current_level = 'L1'
        self._level_cache.clear()

    @QtCore.pyqtSlot(object)
    def set_candles(self, candles: np.ndarray) -> None:
        # Backward-compat; not used by new flow
        self._candles = candles
        n = len(candles)
        self._x_idx = np.arange(n, dtype=float)
        self._up_mask = candles[:, 4] >= candles[:, 1]
        self._dn_mask = ~self._up_mask
        self.renderCandles(candles, [])

    def renderCandles(self, candles: np.ndarray, dts: list) -> None:
        if self._pricePlot is None or candles is None or len(candles) == 0:
            return
        price = self._pricePlot
        vol = self._volPlot
        price.clear()
        vol.clear()

        x = self._x_idx
        o = candles[:, 1]
        h = candles[:, 2]
        l = candles[:, 3]
        c = candles[:, 4]
        v = candles[:, 5]
        up = self._up_mask
        dn = self._dn_mask

        # Wicks
        wick_y = (h + l) / 2.0
        self._wickItem = pg.ErrorBarItem(x=x, y=wick_y, top=h - wick_y, bottom=wick_y - l, beam=0.2, pen=pg.mkPen('#A0A0A0'))
        price.addItem(self._wickItem)

        # Bodies
        width = 0.6
        self._bodyUp = pg.BarGraphItem(x=x[up], height=(c[up] - o[up]), width=width, y0=o[up], brush=pg.mkBrush('#00E676'))
        self._bodyDn = pg.BarGraphItem(x=x[dn], height=(c[dn] - o[dn]), width=width, y0=o[dn], brush=pg.mkBrush('#FF7043'))
        price.addItem(self._bodyUp)
        price.addItem(self._bodyDn)

        # Volume
        if self._showVolume:
            self._volUp = pg.BarGraphItem(x=x[up], height=v[up], width=width, y0=0, brush=pg.mkBrush(0, 230, 118, 140))
            self._volDn = pg.BarGraphItem(x=x[dn], height=v[dn], width=width, y0=0, brush=pg.mkBrush(255, 112, 67, 140))
            vol.addItem(self._volUp)
            vol.addItem(self._volDn)
            vol.enableAutoRange(y=True)

        # Axes labels based on current zoom/level
        self._update_axis_ticks()

        # Price marker
        if c.size:
            self._updatePriceMarker(c[-1])

        # Autoscale and log
        price.enableAutoRange(y=True)
        if self._logEnabled:
            price.setLogMode(y=True)
        # Apply pan/zoom limits based on current dataset
        self._apply_limits()
        # Update RSI if visible
        if self._rsiVisible:
            self._compute_and_draw_rsi(c)
        self._update_data_boundaries()
        if self._awaiting_data_fade:
            self._awaiting_data_fade = False
            self._fade_in()

    def _formatXAxis(self, dts: list, level: str, x0: float, x1: float) -> list:
        ticks = []
        if not dts or self._x_idx is None:
            return ticks
        eastern = tz.gettz("US/Eastern")
        n = len(dts)
        i0 = int(max(0, np.floor(x0)))
        i1 = int(min(n - 1, np.ceil(x1)))
        if i1 <= i0:
            return ticks
        nvis = max(1, i1 - i0 + 1)
        step = max(1, nvis // 8)

        # Choose formatter based on level and visible span
        # Estimate days visible using bar granularity
        level_to_min = {'L1': 1440, 'L2': 1440, 'L3': 30, 'L4': 5, 'L5': 1}
        minutes_per_bar = level_to_min.get(level, 1440)
        days_visible = (nvis * minutes_per_bar) / 1440.0
        if level in ('L1', 'L2'):
            fmt = '%b %Y' if days_visible > 180 else '%b %d'
        elif level == 'L3':
            fmt = '%b %d' if days_visible > 7 else '%m/%d %H:%M'
        else:  # L4, L5
            fmt = '%H:%M' if days_visible < 1.5 else '%b %d %H:%M'

        for i in range(i0, i1 + 1, step):
            try:
                label = dts[i].astimezone(eastern).strftime(fmt)
                ticks.append((i, label))
            except Exception:
                pass
        # Ensure at least two ticks (endpoints) so axis never looks empty
        if not ticks:
            try:
                ticks.append((i0, dts[i0].astimezone(eastern).strftime(fmt)))
            except Exception:
                pass
            if i1 > i0:
                try:
                    ticks.append((i1, dts[i1].astimezone(eastern).strftime(fmt)))
                except Exception:
                    pass
        return ticks

    def _update_axis_ticks(self) -> None:
        if self._pricePlot is None or self._datetimes is None or self._x_idx is None:
            return
        x0, x1 = self._pricePlot.viewRange()[0]
        ticks = self._formatXAxis(self._datetimes, self._current_level, x0, x1)
        if not ticks:
            # Fallback to full-range ticks to avoid empty axis labels
            ticks = self._formatXAxis(self._datetimes, self._current_level, 0.0, float(len(self._x_idx) - 1))
        ax = self._pricePlot.getPlotItem().getAxis('bottom')
        ax.setTicks([ticks])

    def _updatePriceMarker(self, price_val: Optional[float]) -> None:
        if price_val is None or self._pricePlot is None:
            return
        if self._priceLine is None:
            self._priceLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#00E67655', style=QtCore.Qt.DashLine))
            self._pricePlot.addItem(self._priceLine, ignoreBounds=True)
        self._priceLine.setValue(price_val)
        # Simple text at right
        if self._priceLabel is None:
            self._priceLabel = pg.TextItem(color='w', anchor=(1, 0.5), fill=pg.mkBrush('#00E676'))
            self._pricePlot.addItem(self._priceLabel)
        vb = self._pricePlot.getViewBox()
        if vb is not None and self._x_idx is not None and len(self._x_idx) > 0:
            x_right = self._x_idx[-1] + 1
            self._priceLabel.setHtml(f"<span style='color:white; padding:2px'>$ {price_val:,.2f}</span>")
            self._priceLabel.setPos(x_right, price_val)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        try:
            if hasattr(self, "_fade_overlay") and self._fade_overlay is not None and hasattr(self, "_plots_container"):
                self._fade_overlay.setGeometry(self._plots_container.rect())
                self._fade_overlay.raise_()
        except Exception:
            pass

    @QtCore.pyqtSlot(bool)
    def setLogEnabled(self, enabled: bool) -> None:
        self._logEnabled = enabled
        if self._pricePlot:
            self._pricePlot.setLogMode(y=enabled)

    @QtCore.pyqtSlot(bool)
    def setVolumeVisible(self, visible: bool) -> None:
        self._showVolume = visible
        if self._volPlot:
            self._volPlot.setVisible(visible)

    @QtCore.pyqtSlot()
    def resetView(self) -> None:
        def _do_reset():
            if self._pricePlot:
                self._pricePlot.enableAutoRange()
            if self._volPlot:
                self._volPlot.enableAutoRange()
        if self._transitions_enabled:
            self._fade_out(lambda: ( _do_reset(), self._fade_in() ), expect_data=False)
        else:
            _do_reset()

    @QtCore.pyqtSlot(float, float, object)
    def onPrice(self, lastPrice: float, prevClose: float, lastTrade: object) -> None:
        self._updatePriceMarker(lastPrice)

    @QtCore.pyqtSlot(str)
    def onStatus(self, status: str) -> None:
        # Reserved for future small badge
        pass

    def _on_mouse_moved(self, pos):
        if self._pricePlot is None or self._candles is None or self._x_idx is None:
            return
        vb = self._pricePlot.getViewBox()
        if vb is None:
            return
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        idx = int(np.clip(round(x), 0, len(self._x_idx) - 1))
        o = self._candles[idx, 1]
        h = self._candles[idx, 2]
        l = self._candles[idx, 3]
        c = self._candles[idx, 4]
        dt = None
        if self._datetimes and idx < len(self._datetimes):
            dt = self._datetimes[idx]
        self._vline.setValue(idx)
        self._hline.setValue(y)
        dt_str = dt.strftime('%Y-%m-%d') if dt else '—'
        self.lbl_cursor.setText(f"{dt_str}  O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}")

    @QtCore.pyqtSlot(bool)
    def onToggleRSI(self, enabled: bool) -> None:
        self._rsiVisible = enabled
        if self._rsiPlot is None:
            return
        self._rsiPlot.setVisible(enabled)
        if not enabled:
            self._rsiPlot.clear()
            return
        if self._candles is None or self._candles.shape[0] < 15:
            # Not enough data
            self._rsiPlot.clear()
            return
        closes = self._candles[:, 4]
        self._compute_and_draw_rsi(closes)

    @QtCore.pyqtSlot(str)
    def _on_timeframe_selected(self, tf: str) -> None:
        # proxy for type hints; real slot lives on MainWindow
        pass

    def _compute_and_draw_rsi(self, closes: np.ndarray) -> None:
        rsi = _compute_rsi14(closes)
        # Prepare curve
        if self._rsiCurve is None:
            pen = pg.mkPen('#E6F2FF', width=2)
            self._rsiCurve = self._rsiPlot.plot([], [], pen=pen, clipToView=True)
            # Lines and band
            self._rsiPlot.addLine(y=70, pen=pg.mkPen('#FFB74D', width=1.5, style=QtCore.Qt.DashLine))
            self._rsiPlot.addLine(y=30, pen=pg.mkPen('#81C784', width=1.5, style=QtCore.Qt.DashLine))
            self._rsiBand = pg.LinearRegionItem(values=(30, 70), orientation='horizontal', brush=pg.mkBrush(30, 58, 95, 64))
            self._rsiBand.setMovable(False)
            self._rsiPlot.addItem(self._rsiBand)
        x = np.arange(rsi.size, dtype=float)
        self._rsiCurve.setData(x=x, y=rsi)
        self._rsiPlot.setYRange(0, 100, padding=0.02)
        try:
            latest = rsi[~np.isnan(rsi)][-1]
            self.lbl_rsi_value.setText(f"{latest:.2f}")
        except Exception:
            self.lbl_rsi_value.setText("—")

    def _on_range_changed(self, _, ranges):
        # If timeframe lock is active, do not emit level changes; only refresh ticks
        if self._x_idx is None or self._x_idx.size == 0:
            return
        if self._lock_view:
            self._update_axis_ticks()
            return
        # Debounce level emission to avoid flapping
        self._range_timer.start()
        # Always update axis ticks on range changes
        self._update_axis_ticks()

    def _is_full_range(self) -> bool:
        try:
            if self._x_idx is None or self._x_idx.size == 0:
                return False
            x0, x1 = self._pricePlot.viewRange()[0]
            xmax = float(len(self._x_idx) - 1)
            return x0 <= 0.5 and x1 >= xmax - 0.5
        except Exception:
            return False

    def _emit_range_level(self) -> None:
        if self._x_idx is None or self._x_idx.size == 0 or self._lock_view:
            return
        x_range = self._pricePlot.viewRange()[0]
        span = max(x_range[1] - x_range[0], 1e-9)
        level_to_min = {'L1': 1440, 'L2': 1440, 'L3': 30, 'L4': 5, 'L5': 1}
        minutes_per_bar = level_to_min.get(self._current_level, 1440)
        days = span * (minutes_per_bar / 1440.0)
        new_level = self._level_for_span(days)
        if new_level != self._current_level:
            self._current_level = new_level
            try:
                self.requestCandles.emit(new_level)
            except Exception:
                pass
        else:
            if self._current_level in ('L3', 'L4', 'L5') and self._is_full_range():
                try:
                    self.requestCandles.emit('L1')
                    self._current_level = 'L1'
                except Exception:
                    pass

    @QtCore.pyqtSlot(bool)
    def setViewLock(self, lock: bool) -> None:
        self._lock_view = lock
        self._apply_limits()

    def _apply_limits(self) -> None:
        if self._pricePlot is None or self._x_idx is None:
            return
        try:
            x_max = float(len(self._x_idx) - 1)
            if x_max < 0:
                return
            vb_price = self._pricePlot.getViewBox()
            vb_vol = self._volPlot.getViewBox() if self._volPlot else None
            vb_rsi = self._rsiPlot.getViewBox() if self._rsiPlot else None
            min_range = 3.0
            max_range = max(5.0, x_max + 1.0)
            if vb_price:
                vb_price.setLimits(xMin=0.0, xMax=x_max, minXRange=min_range, maxXRange=max_range)
            if vb_vol:
                vb_vol.setLimits(xMin=0.0, xMax=x_max, minXRange=min_range, maxXRange=max_range)
            if vb_rsi:
                vb_rsi.setLimits(xMin=0.0, xMax=x_max, minXRange=min_range, maxXRange=max_range)
        except Exception:
            pass

    def _update_data_boundaries(self) -> None:
        if self._x_idx is None or self._x_idx.size == 0:
            self._data_time_min = None
            self._data_time_max = None
            self._data_time_span = None
            return
        self._data_time_min = float(self._x_idx[0])
        self._data_time_max = float(self._x_idx[-1])
        span = max(1.0, self._data_time_max - self._data_time_min)
        self._data_time_span = span

    def _level_for_span(self, days: float) -> str:
        if days > 180:
            return 'L1'
        if days > 30:
            return 'L2'
        if days > 3:
            return 'L3'
        if days > 0.25:
            return 'L4'
        return 'L5'

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if self._pricePlot and obj is self._pricePlot.viewport():
            if event.type() == QtCore.QEvent.MouseButtonPress:
                self.mousePressEvent(event)  # type: ignore[arg-type]
            elif event.type() == QtCore.QEvent.MouseMove:
                self.mouseMoveEvent(event)  # type: ignore[arg-type]
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                self.mouseReleaseEvent(event)  # type: ignore[arg-type]
            elif event.type() == QtCore.QEvent.Wheel:
                self.wheelEvent(event)  # type: ignore[arg-type]
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self._has_data():
            self._panning_active = True
            self._pan_start_pos = QtCore.QPoint(event.pos())
            self._pan_start_range = self._viewbox.viewRange() if self._viewbox else None
            self._pan_start_view = self._map_to_view(event.pos())
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._panning_active and self._viewbox and self._pan_start_range and self._pan_start_view:
            current_point = self._map_to_view(event.pos())
            if current_point is None:
                return
            delta_x = (current_point.x() - self._pan_start_view.x()) * self._pan_sensitivity
            delta_y = (self._pan_start_view.y() - current_point.y()) * self._pan_sensitivity
            x_min, x_max = self._pan_start_range[0]
            y_min, y_max = self._pan_start_range[1]
            new_x_min = x_min - delta_x
            new_x_max = x_max - delta_x
            new_y_min = y_min - delta_y
            new_y_max = y_max - delta_y
            new_x_min, new_x_max = self._apply_boundary_constraints(new_x_min, new_x_max)
            self._viewbox.setRange(xRange=(new_x_min, new_x_max), yRange=(new_y_min, new_y_max), padding=0)
            self._update_axis_ticks()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self._panning_active:
            self._panning_active = False
            self.setCursor(QtCore.Qt.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
        if not self._has_data() or self._viewbox is None:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        zoom_factor = 1.05 if delta > 0 else 0.95
        x_min, x_max = self._viewbox.viewRange()[0]
        current_span = max(1e-6, x_max - x_min)
        new_span = current_span / zoom_factor
        max_span = self._data_time_span or current_span
        if max_span <= 0:
            event.accept()
            return
        new_span = min(max_span, new_span)
        min_span = min(max_span, max(1.0, self._min_visible_bars))
        if new_span < min_span:
            new_span = min_span
        mouse_point = self._map_to_view(event.pos())
        if mouse_point is None:
            mouse_point = QtCore.QPointF((x_min + x_max) / 2.0, 0.0)
        mouse_x = mouse_point.x()
        left_ratio = 0.5 if current_span == 0 else (mouse_x - x_min) / current_span
        new_x_min = mouse_x - (new_span * left_ratio)
        new_x_max = new_x_min + new_span
        new_x_min, new_x_max = self._apply_boundary_constraints(new_x_min, new_x_max, span=new_span)
        self.animate_view_change((new_x_min, new_x_max))
        event.accept()

    def animate_timeframe_change(self, timeframe: str) -> None:
        if not self._transitions_enabled:
            self.requestTimeframe.emit(timeframe)
            return

        def _request():
            self._awaiting_data_fade = True
            self.requestTimeframe.emit(timeframe)

        self._fade_out(_request, expect_data=True)

    def animate_view_change(
        self,
        new_x_range: Tuple[float, float],
        new_y_range: Optional[Tuple[float, float]] = None,
        duration: Optional[int] = None,
    ) -> None:
        if self._viewbox is None:
            return
        dur = duration if duration is not None else self._zoom_animation_ms
        if dur <= 0:
            self._viewbox.setRange(xRange=new_x_range, yRange=new_y_range, padding=0)
            return
        self._zoom_start_range = self._viewbox.viewRange()
        self._zoom_target_range = (
            new_x_range,
            new_y_range if new_y_range is not None else self._zoom_start_range[1],
        )
        self._zoom_steps = max(1, dur // 16)
        self._zoom_index = 0
        if self._zoom_timer is None:
            self._zoom_timer = QtCore.QTimer(self)
            self._zoom_timer.timeout.connect(self._on_zoom_animation_step)
        self._zoom_timer.start(max(1, dur // self._zoom_steps))

    def _on_zoom_animation_step(self) -> None:
        if (
            self._viewbox is None
            or self._zoom_start_range is None
            or self._zoom_target_range is None
            or self._zoom_steps == 0
        ):
            if self._zoom_timer:
                self._zoom_timer.stop()
            return
        self._zoom_index += 1
        t = min(1.0, self._zoom_index / self._zoom_steps)
        start_x = self._zoom_start_range[0]
        start_y = self._zoom_start_range[1]
        target_x, target_y = self._zoom_target_range
        x_min = start_x[0] + (target_x[0] - start_x[0]) * t
        x_max = start_x[1] + (target_x[1] - start_x[1]) * t
        y_min = start_y[0] + (target_y[0] - start_y[0]) * t
        y_max = start_y[1] + (target_y[1] - start_y[1]) * t
        self._viewbox.setRange(xRange=(x_min, x_max), yRange=(y_min, y_max), padding=0)
        self._update_axis_ticks()
        if self._zoom_index >= self._zoom_steps and self._zoom_timer:
            self._zoom_timer.stop()
            self._zoom_start_range = None
            self._zoom_target_range = None

    def _apply_boundary_constraints(self, x_min: float, x_max: float, span: Optional[float] = None) -> Tuple[float, float]:
        if self._data_time_min is None or self._data_time_max is None:
            return x_min, x_max
        current_span = span if span is not None else (x_max - x_min)
        total_span = self._data_time_span or current_span
        if total_span <= 0:
            return self._data_time_min, self._data_time_max
        if current_span >= total_span:
            return self._data_time_min, self._data_time_max
        if x_min < self._data_time_min:
            x_min = self._data_time_min
            x_max = x_min + current_span
        if x_max > self._data_time_max:
            x_max = self._data_time_max
            x_min = x_max - current_span
        x_min = max(self._data_time_min, x_min)
        x_max = min(self._data_time_max, x_max)
        return x_min, x_max

    def _has_data(self) -> bool:
        return (
            self._viewbox is not None
            and self._x_idx is not None
            and self._x_idx.size > 0
            and self._data_time_min is not None
            and self._data_time_max is not None
        )

    def _map_to_view(self, pos: QtCore.QPoint) -> Optional[QtCore.QPointF]:
        if self._viewbox is None:
            return None
        try:
            scene_pos = self._viewbox.mapViewToScene(pos)
            return self._viewbox.mapSceneToView(scene_pos)
        except Exception:
            return None

    def _fade_out(self, callback: Optional[Callable[[], None]], expect_data: bool) -> None:
        if not self._transitions_enabled:
            if callback:
                callback()
            if not expect_data:
                self._fade_phase = "idle"
                self._fade_in()
            else:
                self._awaiting_data_fade = expect_data
            return
        self._pending_transition_callback = callback
        self._awaiting_data_fade = expect_data
        self._fade_phase = "fading_out"
        self._fade_animation.stop()
        self._fade_overlay.show()
        self._fade_animation.setDuration(self._fade_duration_ms)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(0.7)
        self._fade_overlay.raise_()
        self._fade_animation.start()

    def _fade_in(self) -> None:
        if not self._transitions_enabled:
            self._fade_phase = "idle"
            return
        self._fade_phase = "fading_in"
        self._fade_animation.stop()
        self._fade_animation.setDuration(self._fade_duration_ms)
        self._fade_animation.setStartValue(self._fade_overlay_effect.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def _on_fade_finished(self) -> None:
        if self._fade_phase == "fading_out":
            callback = self._pending_transition_callback
            self._pending_transition_callback = None
            if callback:
                callback()
            if not self._awaiting_data_fade:
                self._fade_in()
        elif self._fade_phase == "fading_in":
            self._fade_phase = "idle"
            self._fade_overlay.hide()

    def _bar_interval_for_level(self, level: str) -> float:
        mapping = {'L1': 86400.0, 'L2': 86400.0, 'L3': 1800.0, 'L4': 300.0, 'L5': 60.0}
        return mapping.get(level, 86400.0)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        k = event.key()
        if k == QtCore.Qt.Key_R:
            self.resetView()
            event.accept()
            return
        if k == QtCore.Qt.Key_V:
            self.chk_vol.setChecked(not self.chk_vol.isChecked())
            event.accept()
            return
        if k == QtCore.Qt.Key_L:
            self.chk_log.setChecked(not self.chk_log.isChecked())
            event.accept()
            return
        if k == QtCore.Qt.Key_I:
            self.chk_rsi.setChecked(not self.chk_rsi.isChecked())
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_tf_clicked(self, tf: str) -> None:
        # Update toggles
        for key, btn in self._tf_buttons.items():
            btn.setChecked(key == tf)
        # Emit timeframe request with optional transition
        self.animate_timeframe_change(tf)

    @QtCore.pyqtSlot(str)
    def setRangeLabel(self, text: str) -> None:
        self.lbl_range.setText(text)

    @QtCore.pyqtSlot(str)
    def setTimeframeSelection(self, tf: str) -> None:
        for key, btn in self._tf_buttons.items():
            btn.setChecked(key == tf)
        self._current_timeframe = tf


class MainWindow(QtWidgets.QMainWindow):
    price_update = QtCore.pyqtSignal(float, float, object)  # price, prev_close, last_trade_dt
    today_update = QtCore.pyqtSignal(object, object, object, object)  # open, high, low, volume
    keys_update = QtCore.pyqtSignal(object, object, object, object, object, object, str)
    company_update = QtCore.pyqtSignal(str, str)
    ws_status_update = QtCore.pyqtSignal(str)
    chart_candles_ready = QtCore.pyqtSignal(object, object, str)
    chart_set_ticker = QtCore.pyqtSignal(str)

    def __init__(self, client: PolygonClient):
        super().__init__()
        ensure_schema()
        auth_dialog = AuthDialog(self)
        session = auth_dialog.exec_()
        if not session:
            QtWidgets.QMessageBox.critical(
                self,
                "Authentication Required",
                "You must log in to use this application.",
            )
            sys.exit(1)
        self.session = session
        self.user_id = self._resolve_user_id(session)
        if not self.user_id:
            QtWidgets.QMessageBox.critical(self, "Authentication Error", "Unable to determine Supabase user id.")
            sys.exit(1)
        try:
            accounts = load_accounts(self.user_id)
        except SupabaseStoreError as exc:
            logger.warning("Unable to load accounts: %s", exc)
            accounts = []
        if accounts:
            self.active_account = accounts[0]
        else:
            self.active_account = create_default_account(
                self.user_id,
                name="Paper-1",
                starting_cash=STARTING_CAPITAL,
            )
        self.client = client
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
            self.tab_info.tapeWidget.setFetchTradesCallback(self.client.fetch_trades_today)
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
        self.tabs.addTab(self.tab_info, "Info")
        self.tabs.addTab(self.tab_chart, "Chart")
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
                    data = self.client.get_aggs_range(ticker, 5, 'minute', start.date().isoformat(), now.date().isoformat())
                    level = 'L4'
                elif tf == '1W':
                    start = now - timedelta(days=7)
                    data = self.client.get_aggs_range(ticker, 30, 'minute', start.date().isoformat(), now.date().isoformat())
                    level = 'L3'
                elif tf == '1M':
                    start = now - timedelta(days=30)
                    data = self.client.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == '3M':
                    start = now - timedelta(days=90)
                    data = self.client.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == 'YTD':
                    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
                    data = self.client.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L2'
                elif tf == '5Y':
                    start = now - timedelta(days=365*5)
                    data = self.client.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
                    level = 'L1'
                else:  # '1Y'
                    start = now - timedelta(days=365)
                    data = self.client.get_aggs_range(ticker, 1, 'day', start.date().isoformat(), now.date().isoformat())
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

    def _resolve_user_id(self, session: Any) -> Optional[str]:
        user = getattr(session, "user", None)
        if user and hasattr(user, "id"):
            return user.id
        if isinstance(session, dict):
            user_dict = session.get("user") or {}
            return user_dict.get("id")
        return None

    # ----------------- Data loading -----------------
    def _load_ticker(self, ticker: str) -> None:
        try:
            # Collect REST data
            details = self.client.get_ticker_details(ticker)
            prev = self.client.get_previous_close(ticker)
            snap = self.client.get_snapshot(ticker)

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
            agg_30 = self.client.get_daily_aggs_range(ticker, start_30.date().isoformat(), end.date().isoformat())
            agg_365 = self.client.get_daily_aggs_range(ticker, start_365.date().isoformat(), end.date().isoformat())

            vols = [(r.get("v") or 0) for r in (agg_30.get("results") or [])[-30:]]
            avg_vol_30d = float(np.mean(vols)) if vols else None
            prices = [
                (float(r.get("h")), float(r.get("l")))
                for r in (agg_365.get("results") or [])
                if r.get("h") is not None and r.get("l") is not None
            ]
            w52h = max([p[0] for p in prices]) if prices else None
            w52l = min([p[1] for p in prices]) if prices else None

            market_status = self.client.et_now_status()

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
            data = self.client.get_daily_aggs_range(ticker, start.isoformat(), end.isoformat())
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
                    data = self.client.get_aggs_range(ticker, 1, 'day', start_dt.date().isoformat(), end_dt.date().isoformat())
                elif level == 'L3':
                    start_dt = end_dt - timedelta(days=30)
                    try:
                        data = self.client.get_aggs_range(ticker, 30, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.client.get_aggs_range(ticker, 1, 'day', start_dt.date().isoformat(), end_dt.date().isoformat())
                elif level == 'L4':
                    start_dt = end_dt - timedelta(days=3)
                    try:
                        data = self.client.get_aggs_range(ticker, 5, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.client.get_aggs_range(ticker, 15, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                else:  # L5
                    start_dt = end_dt - timedelta(days=1)
                    try:
                        data = self.client.get_aggs_range(ticker, 1, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())
                    except Exception:
                        data = self.client.get_aggs_range(ticker, 5, 'minute', start_dt.date().isoformat(), end_dt.date().isoformat())

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
            snap = self.client.get_snapshot(ticker)
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
        try:
            sign_out()
        except Exception as exc:
            logger.debug("Sign out failed: %s", exc)
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


# ----------------- Formatting helpers -----------------
def _fmt_price(val: Optional[float]) -> str:
    if val is None:
        return "—"
    try:
        return f"${val:,.2f}"
    except Exception:
        return "—"


def _fmt_int(val: Optional[float]) -> str:
    if val is None:
        return "—"
    try:
        return f"{int(val):,}"
    except Exception:
        return "—"


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "—"
    try:
        return f"{val:.2f}%"
    except Exception:
        return "—"


def _fmt_dt_et(dt_utc: Optional[datetime]) -> str:
    if not dt_utc:
        return "—"
    eastern = tz.gettz("US/Eastern")
    try:
        et = dt_utc.astimezone(eastern)
        return f"{dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC (ET: {et.strftime('%H:%M:%S')})"
    except Exception:
        return dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')


def _set_color_number(lbl: QtWidgets.QLabel, val: Optional[float], ref: Optional[float]) -> None:
    color = "#444444"
    if val is None or ref is None:
        color = "#444444"
    else:
        if val > ref:
            color = "#2ca02c"  # green
        elif val < ref:
            color = "#d62728"  # red
        else:
            color = "#444444"
    lbl.setStyleSheet(f"color: {color};")


def _ts_to_dt_utc(ts_any: Any) -> datetime:
    try:
        ts = int(ts_any)
        # Heuristic: detect unit by magnitude
        if ts > 1e18:  # too large
            ts = ts / 1e9
        elif ts > 1e15:  # nanoseconds
            ts = ts / 1e9
        elif ts > 1e12:  # microseconds
            ts = ts / 1e6
        elif ts > 1e10:  # milliseconds
            ts = ts / 1e3
        else:  # seconds
            ts = float(ts)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _compute_rsi14(close: np.ndarray) -> np.ndarray:
    n = close.size
    rsi = np.full(n, np.nan, dtype=np.float32)
    if n < 15:
        return rsi
    delta = np.diff(close)
    gain = np.maximum(delta, 0.0)
    loss = np.maximum(-delta, 0.0)
    avgG = gain[:14].mean() if gain[:14].size else 0.0
    avgL = loss[:14].mean() if loss[:14].size else 0.0
    if avgL == 0 and avgG == 0:
        rsi[14] = 50.0
    elif avgL == 0:
        rsi[14] = 100.0
    elif avgG == 0:
        rsi[14] = 0.0
    else:
        rs = avgG / avgL
        rsi[14] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(15, n):
        g = gain[i - 1] if i - 1 < gain.size else 0.0
        l = loss[i - 1] if i - 1 < loss.size else 0.0
        avgG = (avgG * 13.0 + g) / 14.0
        avgL = (avgL * 13.0 + l) / 14.0
        if avgL == 0 and avgG == 0:
            rsi[i] = 50.0
        elif avgL == 0:
            rsi[i] = 100.0
        elif avgG == 0:
            rsi[i] = 0.0
        else:
            rs = avgG / avgL
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi

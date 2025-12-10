from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from dateutil import tz
from PyQt5 import QtCore, QtGui, QtWidgets

from config import (
    CHART_TRANSITION_ENABLED,
    CHART_TRANSITION_DURATION_MS,
    CHART_ZOOM_ANIMATION_DURATION_MS,
)
from src.services.chart_service import compute_rsi14
from src.utils.formatting import _fmt_price, _ts_to_dt_utc


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
        self._pan_sensitivity: float = 0.08  # lower = less responsive pan
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
        rsi = compute_rsi14(closes)
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
        zoom_factor = 1.02 if delta > 0 else 0.98
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

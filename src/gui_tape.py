from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional

import pytz
from PyQt5 import QtCore, QtWidgets

import config


class TapeWidget(QtWidgets.QWidget):
    """Time & Sales tape widget."""

    EXCHANGE_MAP = {
        "1": "NYSE American",
        "2": "NASDAQ BX",
        "3": "NYSE National",
        "4": "NSX",
        "5": "IEX",
        "6": "Cboe EDGA",
        "7": "Cboe EDGX",
        "8": "Cboe BYX",
        "9": "Cboe BZX",
        "10": "MEMX",
        "11": "NASDAQ",
        "12": "NYSE",
        "13": "Investors Exch",
    }

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._current_ticker: Optional[str] = None
        self._current_date: Optional[datetime.date] = None
        self._fetch_trades_cb: Optional[Callable[[str], List[dict]]] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel("Time & Sales")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time (ET)", "Price", "Size", "Exch"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        controls = QtWidgets.QHBoxLayout()
        self.chk_auto_scroll = QtWidgets.QCheckBox("Auto-scroll")
        self.chk_auto_scroll.setChecked(True)
        controls.addWidget(self.chk_auto_scroll)
        controls.addStretch(1)
        layout.addLayout(controls)

    def setFetchTradesCallback(self, callback: Callable[[str], List[dict]]) -> None:
        self._fetch_trades_cb = callback

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._current_date = None

    def loadTicker(self, ticker: str) -> None:
        self._current_ticker = ticker.upper()
        self.clear()
        self._current_date = self._et_today()
        if not self._fetch_trades_cb:
            return
        trades = self._fetch_trades_cb(self._current_ticker)
        for trade in trades:
            self._append_row(trade)
        self._scroll_to_bottom()

    def appendTrade(self, trade: dict) -> None:
        if not trade:
            return
        dt_utc = self._trade_timestamp(trade)
        if not dt_utc:
            return
        trade_date = self._get_et_date(dt_utc)
        if self._current_date and trade_date > self._current_date:
            # rollover
            self.loadTicker(self._current_ticker or "")
            return
        if self._current_date is None:
            self._current_date = trade_date
        at_bottom = self._is_at_bottom()
        self._append_row(trade)
        if at_bottom and self.chk_auto_scroll.isChecked():
            self._scroll_to_bottom()

    def _append_row(self, trade: dict) -> None:
        dt_utc = self._trade_timestamp(trade)
        if not dt_utc:
            return
        dt_et = dt_utc.astimezone(pytz.timezone("America/New_York"))
        price = trade.get("price") or trade.get("p")
        size = trade.get("size") or trade.get("s")
        exchange = trade.get("exchange") or trade.get("x") or ""

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(dt_et.strftime("%H:%M:%S")))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(self._fmt_price(price)))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(self._fmt_size(size)))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(self._fmt_exchange(exchange)))
        self._trim_rows()

    def _trade_timestamp(self, trade: dict) -> Optional[datetime]:
        ts = trade.get("timestamp") or trade.get("t")
        if not ts:
            return None
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            return None
        if ts > 1_000_000_000_000_000:  # ns
            return datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)
        if ts > 1_000_000_000_000:  # microseconds
            return datetime.fromtimestamp(ts / 1_000_000, tz=timezone.utc)
        if ts > 1_000_000_000:  # milliseconds
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    def _is_at_bottom(self) -> bool:
        scrollbar = self.table.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum()

    def _scroll_to_bottom(self) -> None:
        self.table.scrollToBottom()

    def _trim_rows(self) -> None:
        max_rows = getattr(config, "TAPE_MAX_ROWS", 500)
        while self.table.rowCount() > max_rows:
            self.table.removeRow(0)

    @staticmethod
    def _fmt_price(val: Optional[float]) -> str:
        if val is None:
            return "—"
        try:
            return f"${float(val):,.2f}"
        except Exception:
            return "—"

    @staticmethod
    def _fmt_size(val: Optional[int]) -> str:
        if val is None:
            return "—"
        try:
            return f"{int(val):,}"
        except Exception:
            return "—"

    @staticmethod
    def _get_et_date(dt: datetime) -> datetime.date:
        eastern = pytz.timezone("America/New_York")
        return dt.astimezone(eastern).date()

    def _et_today(self) -> datetime.date:
        return self._get_et_date(datetime.now(timezone.utc))

    def _fmt_exchange(self, value: Optional[str]) -> str:
        if value is None:
            return "—"
        key = str(value)
        return self.EXCHANGE_MAP.get(key, key)

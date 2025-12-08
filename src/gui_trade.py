from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.data_models import Fill, Position
from src.oms import Broker
from src.supabase_store import SupabaseStoreError, load_orders


class TradeTab(QtWidgets.QWidget):
    loadTickerRequested = QtCore.pyqtSignal(str)

    def __init__(self, broker: Broker, mark_price_fn: Callable[[str], float], parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.broker = broker
        self.mark_price_fn = mark_price_fn
        self._pending_orders: List[Dict[str, str]] = []
        self._order_rows: Dict[str, int] = {}
        self._order_context: Dict[str, Dict[str, str]] = {}
        self._max_orders = 100
        self._build_ui()
        self._load_existing_orders()
        self.updatePositions(list(self.broker.position_map.values()))
        self.updatePortfolio(self.broker.portfolio_state)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._build_portfolio_header(layout)
        self._build_order_entry(layout)
        self._build_tables(layout)

    def _build_portfolio_header(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Portfolio")
        grid = QtWidgets.QGridLayout()
        self.lbl_equity = QtWidgets.QLabel("$0.00")
        self.lbl_cash = QtWidgets.QLabel("$0.00")
        self.lbl_market_value = QtWidgets.QLabel("$0.00")
        self.lbl_unrealized = QtWidgets.QLabel("$0.00")
        self.lbl_realized = QtWidgets.QLabel("$0.00")
        grid.addWidget(QtWidgets.QLabel("Equity"), 0, 0)
        grid.addWidget(self.lbl_equity, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Cash"), 0, 2)
        grid.addWidget(self.lbl_cash, 0, 3)
        grid.addWidget(QtWidgets.QLabel("Market Value"), 1, 0)
        grid.addWidget(self.lbl_market_value, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Unrealized P&L"), 1, 2)
        grid.addWidget(self.lbl_unrealized, 1, 3)
        grid.addWidget(QtWidgets.QLabel("Realized P&L (Today)"), 2, 0)
        grid.addWidget(self.lbl_realized, 2, 1)
        group.setLayout(grid)
        parent_layout.addWidget(group)

    def _build_order_entry(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Order Entry")
        grid = QtWidgets.QGridLayout()
        self.input_ticker = QtWidgets.QLineEdit()
        self.input_ticker.setMaxLength(5)
        self.combo_side = QtWidgets.QComboBox()
        self.combo_side.addItems(["BUY", "SELL"])
        self.spin_quantity = QtWidgets.QSpinBox()
        self.spin_quantity.setRange(1, 999999)
        self.lbl_order_type = QtWidgets.QLabel("MARKET")
        self.lbl_order_type.setStyleSheet("color: gray;")
        self.btn_submit = QtWidgets.QPushButton("Submit Order")
        self.btn_submit.clicked.connect(self._submit_order)
        self.combo_side.currentTextChanged.connect(self._update_submit_color)
        self._update_submit_color(self.combo_side.currentText())

        grid.addWidget(QtWidgets.QLabel("Ticker"), 0, 0)
        grid.addWidget(self.input_ticker, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Side"), 0, 2)
        grid.addWidget(self.combo_side, 0, 3)
        grid.addWidget(QtWidgets.QLabel("Quantity"), 1, 0)
        grid.addWidget(self.spin_quantity, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Order Type"), 1, 2)
        grid.addWidget(self.lbl_order_type, 1, 3)
        grid.addWidget(self.btn_submit, 2, 0, 1, 4)

        group.setLayout(grid)
        parent_layout.addWidget(group)

        self.status_label = QtWidgets.QLabel("")
        parent_layout.addWidget(self.status_label)

    def _build_tables(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.tbl_positions = QtWidgets.QTableWidget(0, 7)
        self.tbl_positions.setHorizontalHeaderLabels(
            ["Ticker", "Qty", "Avg Cost", "Mark Price", "Market Value", "Unrealized", "Unrealized %"]
        )
        self.tbl_positions.verticalHeader().setVisible(False)
        self.tbl_positions.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_positions.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_positions.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tbl_positions.horizontalHeader().setStretchLastSection(True)
        self.tbl_positions.cellDoubleClicked.connect(self._on_position_double_clicked)
        positions_group = QtWidgets.QGroupBox("Open Positions")
        pos_layout = QtWidgets.QVBoxLayout()
        pos_layout.addWidget(self.tbl_positions)
        positions_group.setLayout(pos_layout)

        self.tbl_orders = QtWidgets.QTableWidget(0, 8)
        self.tbl_orders.setHorizontalHeaderLabels(
            ["Time", "Ticker", "Side", "Qty", "Type", "Status", "Fill Price", "Notes"]
        )
        self.tbl_orders.verticalHeader().setVisible(False)
        self.tbl_orders.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_orders.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_orders.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tbl_orders.horizontalHeader().setStretchLastSection(True)
        orders_group = QtWidgets.QGroupBox("Order Blotter")
        orders_layout = QtWidgets.QVBoxLayout()
        orders_layout.addWidget(self.tbl_orders)
        orders_group.setLayout(orders_layout)

        splitter.addWidget(positions_group)
        splitter.addWidget(orders_group)
        parent_layout.addWidget(splitter)

    def _load_existing_orders(self) -> None:
        try:
            orders = load_orders(self.broker.account.id, limit=self._max_orders)
        except SupabaseStoreError:
            return
        for order in reversed(orders):
            ctx = {
                "ticker": order.ticker,
                "side": order.side,
                "qty": str(order.qty),
                "status": order.status,
            }
            self._append_order_row(order.id, ctx, fill_price=None, timestamp=order.submitted_at)

    def _update_submit_color(self, side: str) -> None:
        color = "#2e7d32" if side == "BUY" else "#c62828"
        self.btn_submit.setStyleSheet(f"font-weight: bold; color: white; background-color: {color}; padding: 8px;")

    def _submit_order(self) -> None:
        ticker = self.input_ticker.text().strip().upper()
        qty = self.spin_quantity.value()
        side = self.combo_side.currentText()
        if not ticker:
            self._set_status("Enter a ticker.")
            return
        self._set_status("")
        self._pending_orders.append({"ticker": ticker, "side": side, "qty": str(qty)})
        try:
            self.broker.submit_market_order(ticker, side, qty)
            self._set_status(f"{side} order submitted for {qty} {ticker}.", error=False)
        except Exception as exc:  # broker handles most errors via signals
            self._set_status(str(exc))

    def updatePositions(self, positions: List[Position]) -> None:
        self.tbl_positions.setRowCount(0)
        for pos in positions:
            row = self.tbl_positions.rowCount()
            self.tbl_positions.insertRow(row)
            mark = self.mark_price_fn(pos.ticker) or 0.0
            market_value = mark * pos.qty
            unrealized = (mark - pos.avg_cost) * pos.qty
            pct = (unrealized / (pos.avg_cost * pos.qty) * 100.0) if pos.avg_cost > 0 and pos.qty else 0.0
            self._set_table_item(self.tbl_positions, row, 0, pos.ticker)
            self._set_table_item(self.tbl_positions, row, 1, f"{pos.qty:,}")
            self._set_table_item(self.tbl_positions, row, 2, self._fmt_price(pos.avg_cost))
            self._set_table_item(self.tbl_positions, row, 3, self._fmt_price(mark))
            self._set_table_item(self.tbl_positions, row, 4, self._fmt_price(market_value))
            pnl_item = QtWidgets.QTableWidgetItem(self._fmt_price(unrealized))
            pnl_item.setForeground(QtGui.QColor("green" if unrealized >= 0 else "red"))
            self.tbl_positions.setItem(row, 5, pnl_item)
            pct_item = QtWidgets.QTableWidgetItem(f"{pct:.2f}%")
            pct_item.setForeground(QtGui.QColor("green" if pct >= 0 else "red"))
            self.tbl_positions.setItem(row, 6, pct_item)

    def updatePortfolio(self, portfolio: dict) -> None:
        equity = portfolio.get("equity", 0.0)
        cash = portfolio.get("cash", 0.0)
        market_value = portfolio.get("market_value", 0.0)
        unrealized = portfolio.get("unrealized_pnl", 0.0)
        realized = portfolio.get("realized_pnl_today", 0.0)
        self.lbl_equity.setText(self._fmt_price(equity))
        self.lbl_cash.setText(self._fmt_price(cash))
        self.lbl_market_value.setText(self._fmt_price(market_value))
        self.lbl_unrealized.setText(self._fmt_price(unrealized))
        self.lbl_realized.setText(self._fmt_price(realized))
        equity_color = "green" if equity >= self.broker.account.starting_cash else "red"
        self.lbl_equity.setStyleSheet(f"color: {equity_color};")
        pnl_color = "green" if unrealized >= 0 else "red"
        self.lbl_unrealized.setStyleSheet(f"color: {pnl_color};")
        realized_color = "green" if realized >= 0 else "red"
        self.lbl_realized.setStyleSheet(f"color: {realized_color};")

    def onOrderAccepted(self, order_id: str) -> None:
        ctx = self._pending_orders.pop(0) if self._pending_orders else {"ticker": "", "side": "", "qty": "0"}
        ctx.setdefault("status", "ACCEPTED")
        self._append_order_row(order_id, ctx)

    def onOrderFilled(self, fill: Fill) -> None:
        row = self._order_rows.get(fill.order_id)
        ctx = self._order_context.get(fill.order_id, {})
        if row is None:
            ctx = {
                "ticker": fill.ticker,
                "side": fill.side,
                "qty": str(fill.qty),
                "status": "FILLED",
            }
            row = self._append_order_row(fill.order_id, ctx, fill_price=fill.price)
        self.tbl_orders.setItem(row, 5, QtWidgets.QTableWidgetItem("FILLED"))
        price_item = QtWidgets.QTableWidgetItem(self._fmt_price(fill.price))
        self.tbl_orders.setItem(row, 6, price_item)
        ctx["status"] = "FILLED"
        self._order_context[fill.order_id] = ctx

    def _append_order_row(
        self,
        order_id: str,
        ctx: Dict[str, str],
        fill_price: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        while self.tbl_orders.rowCount() >= self._max_orders:
            self._drop_oldest_order()
        row = self.tbl_orders.rowCount()
        self.tbl_orders.insertRow(row)
        ts = timestamp or datetime.now()
        time_item = QtWidgets.QTableWidgetItem(ts.strftime("%H:%M:%S"))
        self.tbl_orders.setItem(row, 0, time_item)
        ticker = ctx.get("ticker", "")
        side = ctx.get("side", "")
        qty = ctx.get("qty", "0")
        status = ctx.get("status", "ACCEPTED")
        notes = ctx.get("notes", "")
        self._set_table_item(self.tbl_orders, row, 1, ticker)
        side_item = QtWidgets.QTableWidgetItem(side)
        side_item.setForeground(QtGui.QColor("green" if side == "BUY" else "red"))
        self.tbl_orders.setItem(row, 2, side_item)
        self._set_table_item(self.tbl_orders, row, 3, qty)
        self._set_table_item(self.tbl_orders, row, 4, "MARKET")
        self._set_table_item(self.tbl_orders, row, 5, status)
        self._set_table_item(self.tbl_orders, row, 6, self._fmt_price(fill_price) if fill_price else "—")
        self._set_table_item(self.tbl_orders, row, 7, notes)
        self._order_rows[order_id] = row
        self._order_context[order_id] = ctx
        return row

    def _drop_oldest_order(self) -> None:
        if self.tbl_orders.rowCount() == 0:
            return
        removed_order = None
        for oid, idx in list(self._order_rows.items()):
            if idx == 0:
                removed_order = oid
                del self._order_rows[oid]
            else:
                self._order_rows[oid] = idx - 1
        if removed_order:
            self._order_context.pop(removed_order, None)
        self.tbl_orders.removeRow(0)

    def _set_table_item(self, table: QtWidgets.QTableWidget, row: int, col: int, text: str) -> None:
        table.setItem(row, col, QtWidgets.QTableWidgetItem(text))

    def _fmt_price(self, value: Optional[float]) -> str:
        from src.utils.formatting import _fmt_price

        return _fmt_price(value)

    def _on_position_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        ticker_item = self.tbl_positions.item(row, 0)
        if not ticker_item:
            return
        self.loadTickerRequested.emit(ticker_item.text())

    def _set_status(self, text: str, error: bool = True) -> None:
        color = "red" if error else "green"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

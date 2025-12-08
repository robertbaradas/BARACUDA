from __future__ import annotations

import logging
import random
from typing import Callable, Dict, List, Literal, Optional

from PyQt5 import QtCore

import config
from src import portfolio
from src.data_models import Account, Fill, Position
from src.supabase_store import (
    SupabaseStoreError,
    insert_fill,
    insert_ledger,
    insert_order,
    insert_snapshot,
    load_positions,
    upsert_position,
    update_order_status,
)

logger = logging.getLogger(__name__)


class Broker(QtCore.QObject):
    """Simple synchronous paper-trading broker."""

    orderAccepted = QtCore.pyqtSignal(str)
    orderFilled = QtCore.pyqtSignal(object)
    positionsUpdated = QtCore.pyqtSignal(list)
    portfolioUpdated = QtCore.pyqtSignal(dict)
    omsError = QtCore.pyqtSignal(str)

    def __init__(self, account: Account, mark_price_fn: Callable[[str], float]):
        super().__init__()
        self.account = account
        self.mark_price_fn = mark_price_fn
        self.position_map: Dict[str, Position] = {}
        self.cash = float(account.cash or account.starting_cash)
        self.realized_pnl_today = 0.0
        self.portfolio_state = {
            "equity": float(account.equity or self.cash),
            "cash": self.cash,
            "market_value": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl_today": 0.0,
        }
        self._load_positions()
        self.refresh_portfolio()

    def _load_positions(self) -> None:
        try:
            positions = load_positions(self.account.id)
            self.position_map = {pos.ticker.upper(): pos for pos in positions}
            self.positionsUpdated.emit(list(self.position_map.values()))
        except SupabaseStoreError as exc:
            logger.warning("Unable to load positions: %s", exc)

    def submit_market_order(self, ticker: str, side: Literal["BUY", "SELL"], qty: int) -> None:
        ticker = ticker.upper()
        if qty <= 0:
            self.omsError.emit("Quantity must be greater than zero.")
            return

        mark_price = self.mark_price_fn(ticker)
        if mark_price <= 0:
            self.omsError.emit("Unable to determine mark price.")
            return

        fill_price = self._apply_slippage(mark_price)
        est_fee = self._calculate_fee(qty)
        notional = fill_price * qty

        if side == "BUY" and self.cash < (notional + est_fee):
            self.omsError.emit("Insufficient cash for order.")
            return

        if side == "SELL":
            position = self.position_map.get(ticker)
            if not position or position.qty < qty:
                self.omsError.emit("Insufficient quantity to sell.")
                return

        try:
            order_id = insert_order(
                account_id=self.account.id,
                ticker=ticker,
                side=side,
                qty=qty,
                order_type="MARKET",
                status="ACCEPTED",
            )
        except SupabaseStoreError as exc:
            self.omsError.emit(str(exc))
            return

        self.orderAccepted.emit(order_id)

        fee = self._calculate_fee(qty)
        fill_obj = Fill(
            id="",
            order_id=order_id,
            account_id=self.account.id,
            ticker=ticker,
            side=side,
            qty=qty,
            price=fill_price,
            fee=fee,
            filled_at=None,
        )

        try:
            insert_fill(
                order_id=order_id,
                account_id=self.account.id,
                ticker=ticker,
                side=side,
                qty=qty,
                price=fill_price,
                fee=fee,
            )
        except SupabaseStoreError as exc:
            self.omsError.emit(str(exc))
            return

        try:
            updated_positions, cash_delta, realized = portfolio.apply_fill(self.account, self.position_map, fill_obj)
        except ValueError as exc:
            self.omsError.emit(str(exc))
            return

        self.position_map = updated_positions
        self.cash += cash_delta
        self.realized_pnl_today += realized
        self.account.cash = self.cash
        self.account.equity = portfolio.compute_equity(self.cash, self.portfolio_state.get("market_value", 0.0))

        try:
            if ticker in self.position_map:
                pos = self.position_map[ticker]
                upsert_position(self.account.id, ticker, pos.qty, pos.avg_cost)
            else:
                upsert_position(self.account.id, ticker, 0, 0.0)
            insert_ledger(
                account_id=self.account.id,
                amount=cash_delta,
                balance_after=self.cash,
                entry_type="TRADE",
                reference_id=order_id,
            )
            update_order_status(order_id, "FILLED")
        except SupabaseStoreError as exc:
            self.omsError.emit(str(exc))
            return

        self.refresh_portfolio()
        try:
            insert_snapshot(
                account_id=self.account.id,
                equity=self.portfolio_state["equity"],
                cash=self.cash,
                market_value=self.portfolio_state["market_value"],
                unrealized_pnl=self.portfolio_state["unrealized_pnl"],
                realized_pnl=self.realized_pnl_today,
            )
        except SupabaseStoreError as exc:
            logger.debug("Snapshot insert failed: %s", exc)

        self.orderFilled.emit(fill_obj)
        self.positionsUpdated.emit(list(self.position_map.values()))

    def refresh_portfolio(self) -> None:
        positions = list(self.position_map.values())
        unrealized, market_value = portfolio.revalue(positions, self.mark_price_fn)
        equity = portfolio.compute_equity(self.cash, market_value)
        self.portfolio_state = {
            "equity": equity,
            "cash": self.cash,
            "market_value": market_value,
            "unrealized_pnl": unrealized,
            "realized_pnl_today": self.realized_pnl_today,
        }
        self.portfolioUpdated.emit(self.portfolio_state.copy())

    def get_position(self, ticker: str) -> Optional[Position]:
        return self.position_map.get(ticker.upper())

    def get_buying_power(self) -> float:
        return self.cash

    def _apply_slippage(self, price: float) -> float:
        if not config.ENABLE_SLIPPAGE:
            return price
        bps = config.SLIPPAGE_BPS or 0
        delta = random.uniform(-bps, bps) / 10000.0
        return price * (1 + delta)

    def _calculate_fee(self, qty: int) -> float:
        if not config.ENABLE_COMMISSION:
            return 0.0
        per_share = config.COMMISSION_PER_SHARE or 0.0
        fee = max(qty * per_share, config.MIN_COMMISSION or 0.0)
        return fee

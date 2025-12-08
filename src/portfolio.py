from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Callable, Dict, List, Tuple

from src.data_models import Account, Fill, Position

getcontext().prec = 12


def apply_fill(
    account: Account,
    position_map: Dict[str, Position],
    fill: Fill,
) -> Tuple[Dict[str, Position], float, float]:
    """Apply a fill to the in-memory position map."""
    ticker = fill.ticker.upper()
    updated_map = dict(position_map)
    existing = updated_map.get(ticker)
    current_qty = existing.qty if existing else 0
    avg_cost = Decimal(str(existing.avg_cost if existing else 0.0))

    qty = int(fill.qty)
    price = Decimal(str(fill.price))
    fee = Decimal(str(fill.fee or 0.0))

    cash_delta: Decimal
    realized_pnl: Decimal
    new_qty: int
    new_avg_cost: Decimal

    if fill.side == "BUY":
        new_qty = current_qty + qty
        if new_qty <= 0:
            raise ValueError("Resulting quantity must be positive for buy fills.")
        total_cost = avg_cost * Decimal(current_qty) + price * Decimal(qty)
        new_avg_cost = total_cost / Decimal(new_qty)
        cash_delta = -(price * qty + fee)
        realized_pnl = -fee
    else:
        if current_qty < qty:
            raise ValueError("Insufficient quantity to sell.")
        new_qty = current_qty - qty
        new_avg_cost = avg_cost
        cash_delta = price * qty - fee
        realized_pnl = Decimal(qty) * (price - avg_cost) - fee

    if new_qty == 0:
        updated_map.pop(ticker, None)
    else:
        updated_map[ticker] = Position(
            id=existing.id if existing else None,
            account_id=account.id,
            ticker=ticker,
            qty=new_qty,
            avg_cost=float(new_avg_cost),
            updated_at=None,
        )

    return updated_map, float(cash_delta), float(realized_pnl)


def revalue(
    positions: List[Position],
    mark_price_fn: Callable[[str], float],
) -> Tuple[float, float]:
    """Return unrealized PnL and market value for open positions."""
    total_unrealized = Decimal("0")
    total_value = Decimal("0")
    for pos in positions:
        mark = Decimal(str(mark_price_fn(pos.ticker)))
        qty = Decimal(pos.qty)
        avg_cost = Decimal(str(pos.avg_cost))
        total_value += mark * qty
        total_unrealized += (mark - avg_cost) * qty
    return float(total_unrealized), float(total_value)


def compute_equity(cash: float, market_value: float) -> float:
    """Return total equity as cash + market value."""
    return float(Decimal(str(cash)) + Decimal(str(market_value)))

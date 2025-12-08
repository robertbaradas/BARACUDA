from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import config
from src.auth_client import AuthError, get_supabase_client
from src.data_models import Account, Fill, Order, Position, PortfolioSnapshot

logger = logging.getLogger(__name__)

try:
    from postgrest import APIError as PostgrestAPIError  # type: ignore
except Exception:  # pragma: no cover - dependency optional in dev env
    PostgrestAPIError = Exception  # type: ignore


class SupabaseStoreError(RuntimeError):
    """Raised for Supabase interaction errors."""


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  base_ccy TEXT DEFAULT 'USD',
  starting_cash NUMERIC(15,2) DEFAULT 10000.00,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, name)
);

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  qty INTEGER NOT NULL CHECK (qty > 0),
  order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP')),
  limit_price NUMERIC(15,4) NULL,
  stop_price NUMERIC(15,4) NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED', 'FILLED', 'PARTIAL', 'CANCELLED', 'REJECTED')),
  submitted_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS fills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  qty INTEGER NOT NULL CHECK (qty > 0),
  price NUMERIC(15,4) NOT NULL,
  fee NUMERIC(15,4) DEFAULT 0.0,
  filled_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE fills ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  qty INTEGER NOT NULL,
  avg_cost NUMERIC(15,4) NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(account_id, ticker)
);

ALTER TABLE positions ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  amount NUMERIC(15,2) NOT NULL,
  balance_after NUMERIC(15,2) NOT NULL,
  entry_type TEXT NOT NULL CHECK (entry_type IN ('INITIAL', 'TRADE', 'FEE', 'DIVIDEND', 'DEPOSIT', 'WITHDRAWAL')),
  reference_id UUID NULL,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE ledger ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  equity NUMERIC(15,2) NOT NULL,
  cash NUMERIC(15,2) NOT NULL,
  market_value NUMERIC(15,2) NOT NULL,
  unrealized_pnl NUMERIC(15,2) NOT NULL,
  realized_pnl NUMERIC(15,2) NOT NULL,
  snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS ml_regimes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker TEXT NOT NULL,
  window TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  cluster_id INTEGER NOT NULL CHECK (cluster_id IN (0, 1, 2)),
  pct_ask NUMERIC(5,2),
  pct_bid NUMERIC(5,2),
  avg_spread NUMERIC(10,4),
  avg_trade_size NUMERIC(12,2),
  volatility NUMERIC(10,6),
  volume_zscore NUMERIC(8,4),
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(ticker, window, window_start)
);

ALTER TABLE ml_regimes ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS ml_forecasts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  as_of_date TIMESTAMPTZ NOT NULL,
  prob_cluster_0 NUMERIC(5,4) NOT NULL,
  prob_cluster_1 NUMERIC(5,4) NOT NULL,
  prob_cluster_2 NUMERIC(5,4) NOT NULL,
  model_type TEXT NOT NULL,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(ticker, timeframe, as_of_date)
);

ALTER TABLE ml_forecasts ENABLE ROW LEVEL SECURITY;
"""

_TABLES = [
    "profiles",
    "accounts",
    "orders",
    "fills",
    "positions",
    "ledger",
    "portfolio_snapshots",
    "ml_regimes",
    "ml_forecasts",
]


def _client(use_session: bool = True):
    try:
        return get_supabase_client(use_session=use_session)
    except AuthError as exc:  # pragma: no cover - requires Supabase creds
        raise SupabaseStoreError(str(exc)) from exc


def _rows(resp: Any) -> List[Dict[str, Any]]:
    data = getattr(resp, "data", None)
    if data is None and isinstance(resp, dict):
        data = resp.get("data")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def _first_row(resp: Any) -> Dict[str, Any]:
    rows = _rows(resp)
    return rows[0] if rows else {}


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _row_to_account(row: Dict[str, Any]) -> Account:
    starting_cash = float(row.get("starting_cash") or config.STARTING_CAPITAL)
    cash = float(row.get("cash") or starting_cash)
    equity = float(row.get("equity") or starting_cash)
    return Account(
        id=row.get("id"),
        user_id=row.get("user_id"),
        name=row.get("name"),
        base_ccy=row.get("base_ccy") or "USD",
        starting_cash=starting_cash,
        cash=cash,
        equity=equity,
        created_at=_parse_dt(row.get("created_at")),
        updated_at=_parse_dt(row.get("updated_at")),
    )


def _row_to_position(row: Dict[str, Any]) -> Position:
    return Position(
        id=row.get("id"),
        account_id=row.get("account_id"),
        ticker=row.get("ticker"),
        qty=int(row.get("qty") or 0),
        avg_cost=float(row.get("avg_cost") or 0.0),
        updated_at=_parse_dt(row.get("updated_at")),
    )


def _row_to_order(row: Dict[str, Any]) -> Order:
    return Order(
        id=row.get("id"),
        account_id=row.get("account_id"),
        ticker=row.get("ticker"),
        side=row.get("side"),
        qty=int(row.get("qty") or 0),
        order_type=row.get("order_type"),
        status=row.get("status"),
        limit_price=row.get("limit_price"),
        stop_price=row.get("stop_price"),
        submitted_at=_parse_dt(row.get("submitted_at")),
        updated_at=_parse_dt(row.get("updated_at")),
    )


def _row_to_fill(row: Dict[str, Any]) -> Fill:
    return Fill(
        id=row.get("id"),
        order_id=row.get("order_id"),
        account_id=row.get("account_id"),
        ticker=row.get("ticker"),
        side=row.get("side"),
        qty=int(row.get("qty") or 0),
        price=float(row.get("price") or 0.0),
        fee=float(row.get("fee") or 0.0),
        filled_at=_parse_dt(row.get("filled_at")),
    )


def _row_to_snapshot(row: Dict[str, Any]) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=row.get("id"),
        account_id=row.get("account_id"),
        equity=float(row.get("equity") or 0.0),
        cash=float(row.get("cash") or 0.0),
        market_value=float(row.get("market_value") or 0.0),
        unrealized_pnl=float(row.get("unrealized_pnl") or 0.0),
        realized_pnl=float(row.get("realized_pnl") or 0.0),
        snapshot_at=_parse_dt(row.get("snapshot_at")),
    )


def ensure_schema() -> None:
    """Attempt to create required tables; fall back to validation if RPC unavailable."""
    try:
        client = _client(use_session=False)
    except SupabaseStoreError as exc:
        logger.debug("Supabase not configured; skipping schema ensure: %s", exc)
        return

    try:  # pragma: no cover - depends on Supabase RPC setup
        client.rpc("exec_sql", {"sql": _SCHEMA_SQL}).execute()
        logger.info("Supabase schema ensured via exec_sql RPC.")
        return
    except Exception as exc:
        logger.debug("exec_sql RPC unavailable: %s", exc)

    missing: List[str] = []
    for table in _TABLES:
        try:
            client.table(table).select("id").limit(1).execute()
        except PostgrestAPIError:
            missing.append(table)
        except Exception as exc:  # pragma: no cover - requires Supabase
            logger.debug("Schema check failed for %s: %s", table, exc)
            missing.append(table)
    if missing:
        logger.warning(
            "Missing Supabase tables: %s. Run the SQL defined in CHANGE_SPEC_PHASE2.xml.",
            ", ".join(missing),
        )


def create_default_account(
    user_id: str,
    name: str = "Paper-1",
    starting_cash: Optional[float] = None,
) -> Account:
    client = _client()
    cash = starting_cash if starting_cash is not None else config.STARTING_CAPITAL
    payload = {
        "user_id": user_id,
        "name": name,
        "base_ccy": "USD",
        "starting_cash": cash,
    }
    try:
        resp = client.table("accounts").insert(payload).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to create account: {exc}") from exc
    row = _first_row(resp)
    account = _row_to_account(row)
    insert_ledger(account.id, amount=cash, balance_after=cash, entry_type="INITIAL")
    return account


def load_accounts(user_id: str) -> List[Account]:
    client = _client()
    try:
        resp = (
            client.table("accounts")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to load accounts: {exc}") from exc
    return [_row_to_account(row) for row in _rows(resp)]


def load_positions(account_id: str) -> List[Position]:
    client = _client()
    try:
        resp = (
            client.table("positions")
            .select("*")
            .eq("account_id", account_id)
            .order("ticker", desc=False)
            .execute()
        )
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to load positions: {exc}") from exc
    return [_row_to_position(row) for row in _rows(resp)]


def upsert_position(account_id: str, ticker: str, qty: int, avg_cost: float) -> None:
    client = _client()
    ticker = ticker.upper()
    try:
        if qty == 0:
            client.table("positions").delete().eq("account_id", account_id).eq("ticker", ticker).execute()
        else:
            payload = {
                "account_id": account_id,
                "ticker": ticker,
                "qty": qty,
                "avg_cost": avg_cost,
            }
            client.table("positions").upsert(payload, on_conflict="account_id,ticker").execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to upsert position: {exc}") from exc


def insert_order(
    account_id: str,
    ticker: str,
    side: str,
    qty: int,
    order_type: str,
    status: str = "PENDING",
) -> str:
    client = _client()
    payload = {
        "account_id": account_id,
        "ticker": ticker.upper(),
        "side": side,
        "qty": qty,
        "order_type": order_type,
        "status": status,
    }
    try:
        resp = client.table("orders").insert(payload).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to insert order: {exc}") from exc
    row = _first_row(resp)
    return row.get("id")


def update_order_status(order_id: str, status: str) -> None:
    client = _client()
    try:
        client.table("orders").update({"status": status}).eq("id", order_id).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to update order status: {exc}") from exc


def insert_fill(
    order_id: str,
    account_id: str,
    ticker: str,
    side: str,
    qty: int,
    price: float,
    fee: float = 0.0,
) -> str:
    client = _client()
    payload = {
        "order_id": order_id,
        "account_id": account_id,
        "ticker": ticker.upper(),
        "side": side,
        "qty": qty,
        "price": price,
        "fee": fee,
    }
    try:
        resp = client.table("fills").insert(payload).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to insert fill: {exc}") from exc
    row = _first_row(resp)
    return row.get("id")


def insert_ledger(
    account_id: str,
    amount: float,
    balance_after: float,
    entry_type: str,
    reference_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    client = _client()
    payload = {
        "account_id": account_id,
        "amount": amount,
        "balance_after": balance_after,
        "entry_type": entry_type,
        "reference_id": reference_id,
        "notes": notes,
    }
    try:
        client.table("ledger").insert(payload).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to insert ledger entry: {exc}") from exc


def insert_snapshot(
    account_id: str,
    equity: float,
    cash: float,
    market_value: float,
    unrealized_pnl: float,
    realized_pnl: float,
) -> PortfolioSnapshot:
    client = _client()
    payload = {
        "account_id": account_id,
        "equity": equity,
        "cash": cash,
        "market_value": market_value,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
    }
    try:
        resp = client.table("portfolio_snapshots").insert(payload).execute()
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to insert snapshot: {exc}") from exc
    row = _first_row(resp)
    return _row_to_snapshot(row)


def load_orders(account_id: str, limit: int = 100) -> List[Order]:
    client = _client()
    try:
        resp = (
            client.table("orders")
            .select("*")
            .eq("account_id", account_id)
            .order("submitted_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to load orders: {exc}") from exc
    return [_row_to_order(row) for row in _rows(resp)]


def load_fills(account_id: str, limit: int = 100) -> List[Fill]:
    client = _client()
    try:
        resp = (
            client.table("fills")
            .select("*")
            .eq("account_id", account_id)
            .order("filled_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        raise SupabaseStoreError(f"Unable to load fills: {exc}") from exc
    return [_row_to_fill(row) for row in _rows(resp)]


def load_positions_map(account_id: str) -> Dict[str, Position]:
    """Convenience helper when Broker initializes."""
    positions = load_positions(account_id)
    return {pos.ticker.upper(): pos for pos in positions}


from datetime import datetime, timezone
from typing import Any, Optional

from dateutil import tz
from PyQt5 import QtWidgets


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

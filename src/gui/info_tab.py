from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from PyQt5 import QtWidgets

from src.gui.news_widget import NewsWidget
from src.gui_tape import TapeWidget
from src.utils.formatting import (
    _fmt_price,
    _fmt_int,
    _fmt_pct,
    _fmt_dt_et,
    _set_color_number,
)


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

        # News Widget
        self.news_widget = NewsWidget()
        self.layout.addWidget(self.news_widget)

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

    def set_news_callbacks(
        self,
        fetch_news: Callable[[str, int], List[dict]],
        fetch_change: Callable[[str], Optional[float]],
    ) -> None:
        """Set callback functions for fetching news and ticker changes."""
        self.news_widget.set_callbacks(fetch_news, fetch_change)

    def load_news(self, ticker: str) -> None:
        """Load news for the specified ticker."""
        self.news_widget.load_news(ticker)

"""
News Widget for BARACUDA
Displays recent news articles for the selected ticker.
"""

from __future__ import annotations

import webbrowser
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.theme import Colors


class TickerBadge(QtWidgets.QPushButton):
    """
    Clickable ticker badge showing symbol and daily change.
    Green if positive, red if negative.
    """

    ticker_clicked = QtCore.pyqtSignal(str)  # Emits ticker symbol when clicked

    def __init__(
        self, ticker: str, change_pct: Optional[float] = None, parent: Optional[QtWidgets.QWidget] = None
    ):
        super().__init__(parent)
        self.ticker = ticker
        self.change_pct = change_pct
        self._setup_ui()
        self.clicked.connect(self._on_clicked)

    def _setup_ui(self) -> None:
        if self.change_pct is not None:
            sign = "+" if self.change_pct >= 0 else ""
            self.setText(f"{self.ticker} {sign}{self.change_pct:.2f}%")
            color = Colors.POSITIVE if self.change_pct >= 0 else Colors.NEGATIVE
        else:
            self.setText(self.ticker)
            color = Colors.TEXT_SECONDARY

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {color};
                border: none;
                font-weight: bold;
                font-size: 12px;
                padding: 2px 6px;
                text-align: left;
            }}
            QPushButton:hover {{
                text-decoration: underline;
            }}
        """)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

    def _on_clicked(self) -> None:
        self.ticker_clicked.emit(self.ticker)


class NewsArticleWidget(QtWidgets.QFrame):
    """
    Single news article display with headline, source, time, and ticker badges.
    """

    ticker_clicked = QtCore.pyqtSignal(str)  # Emits when a ticker badge is clicked
    article_clicked = QtCore.pyqtSignal(str)  # Emits article URL when headline clicked

    def __init__(
        self,
        article: dict,
        ticker_changes: Dict[str, float],
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.article = article
        self.ticker_changes = ticker_changes  # {ticker: change_pct}
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_SURFACE};
                border: none;
                border-bottom: 1px solid {Colors.BORDER_SUBTLE};
                padding: 8px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Row 1: Publisher and time
        header_layout = QtWidgets.QHBoxLayout()

        publisher_name = self.article.get("publisher", {}).get("name", "Unknown")
        published_utc = self.article.get("published_utc", "")
        time_ago = self._format_time_ago(published_utc)

        lbl_source = QtWidgets.QLabel(publisher_name)
        lbl_source.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: bold; font-size: 11px;"
        )
        header_layout.addWidget(lbl_source)

        lbl_time = QtWidgets.QLabel(time_ago)
        lbl_time.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        header_layout.addWidget(lbl_time)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Row 2: Headline (clickable)
        title = self.article.get("title", "No title")
        lbl_title = QtWidgets.QLabel(title)
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            font-size: 13px;
        """)
        lbl_title.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        lbl_title.mousePressEvent = lambda e: self._on_title_clicked()
        layout.addWidget(lbl_title)

        # Row 3: Ticker badges
        tickers = self.article.get("tickers", [])
        if tickers:
            ticker_layout = QtWidgets.QHBoxLayout()
            ticker_layout.setSpacing(12)

            for ticker in tickers[:5]:  # Limit to 5 tickers per article
                change = self.ticker_changes.get(ticker)
                badge = TickerBadge(ticker, change)
                badge.ticker_clicked.connect(self.ticker_clicked.emit)
                ticker_layout.addWidget(badge)

            ticker_layout.addStretch()
            layout.addLayout(ticker_layout)

    def _format_time_ago(self, utc_string: str) -> str:
        """Convert UTC timestamp to relative time (e.g., '2h', '3d')."""
        if not utc_string:
            return ""
        try:
            # Parse ISO format
            published = datetime.fromisoformat(utc_string.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - published

            if delta.days > 0:
                return f"{delta.days}d"
            elif delta.seconds >= 3600:
                return f"{delta.seconds // 3600}h"
            elif delta.seconds >= 60:
                return f"{delta.seconds // 60}m"
            else:
                return "now"
        except Exception:
            return ""

    def _on_title_clicked(self) -> None:
        url = self.article.get("article_url", "")
        if url:
            self.article_clicked.emit(url)


class NewsWidget(QtWidgets.QWidget):
    """
    News feed widget showing recent articles for a ticker.
    """

    ticker_requested = QtCore.pyqtSignal(str)  # Emits when user clicks a different ticker

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.current_ticker: Optional[str] = None
        self.fetch_news_callback: Optional[Callable[[str, int], List[dict]]] = None
        self.fetch_change_callback: Optional[Callable[[str], Optional[float]]] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QtWidgets.QLabel("News")
        header.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            font-size: 14px;
            font-weight: bold;
            padding: 8px;
            background-color: {Colors.BG_ELEVATED};
            border-bottom: 1px solid {Colors.BORDER_SUBTLE};
        """)
        layout.addWidget(header)

        # Scroll area for articles
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {Colors.BG_SURFACE};
            }}
        """)

        self.articles_container = QtWidgets.QWidget()
        self.articles_layout = QtWidgets.QVBoxLayout(self.articles_container)
        self.articles_layout.setContentsMargins(0, 0, 0, 0)
        self.articles_layout.setSpacing(0)
        self.articles_layout.addStretch()

        scroll.setWidget(self.articles_container)
        layout.addWidget(scroll)

        # Loading/empty state label
        self.lbl_status = QtWidgets.QLabel("Enter a ticker to see news")
        self.lbl_status.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_status.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: 20px;")
        self.articles_layout.insertWidget(0, self.lbl_status)

    def set_callbacks(
        self,
        fetch_news: Callable[[str, int], List[dict]],
        fetch_change: Callable[[str], Optional[float]],
    ) -> None:
        """Set callback functions for fetching news and ticker changes."""
        self.fetch_news_callback = fetch_news
        self.fetch_change_callback = fetch_change

    def load_news(self, ticker: str) -> None:
        """Load news for the specified ticker."""
        self.current_ticker = ticker
        self._clear_articles()

        if not self.fetch_news_callback:
            self.lbl_status.setText("News not configured")
            self.lbl_status.setVisible(True)
            return

        self.lbl_status.setText("Loading news...")
        self.lbl_status.setVisible(True)

        # Fetch news in background thread to avoid UI freeze
        QtCore.QTimer.singleShot(0, lambda: self._fetch_and_display(ticker))

    def _fetch_and_display(self, ticker: str) -> None:
        """Fetch news and display articles."""
        try:
            articles = self.fetch_news_callback(ticker, 5)

            if not articles:
                self.lbl_status.setText(f"No recent news for {ticker}")
                self.lbl_status.setVisible(True)
                return

            self.lbl_status.setVisible(False)

            # Collect all unique tickers mentioned in articles
            all_tickers: set = set()
            for article in articles:
                all_tickers.update(article.get("tickers", []))

            # Fetch change percentages for all tickers
            ticker_changes: Dict[str, float] = {}
            if self.fetch_change_callback:
                for t in all_tickers:
                    try:
                        change = self.fetch_change_callback(t)
                        if change is not None:
                            ticker_changes[t] = change
                    except Exception:
                        pass

            # Create article widgets
            for article in articles:
                widget = NewsArticleWidget(article, ticker_changes)
                widget.ticker_clicked.connect(self._on_ticker_clicked)
                widget.article_clicked.connect(self._on_article_clicked)
                # Insert before the stretch
                self.articles_layout.insertWidget(
                    self.articles_layout.count() - 1, widget
                )

        except Exception as e:
            self.lbl_status.setText(f"Error loading news: {e!s}")
            self.lbl_status.setVisible(True)

    def _clear_articles(self) -> None:
        """Remove all article widgets."""
        while self.articles_layout.count() > 1:  # Keep the stretch
            item = self.articles_layout.takeAt(0)
            if item.widget() and item.widget() != self.lbl_status:
                item.widget().deleteLater()

    def _on_ticker_clicked(self, ticker: str) -> None:
        """Handle ticker badge click."""
        if ticker != self.current_ticker:
            self.ticker_requested.emit(ticker)

    def _on_article_clicked(self, url: str) -> None:
        """Open article URL in browser."""
        webbrowser.open(url)

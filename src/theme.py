"""
Trading Terminal Theme Module

Provides a professional dark trading terminal theme (DXtrade XT / Bloomberg-style)
for the BARACUDA application.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QApplication, QLabel


class Colors:
    """Color constants for the trading terminal theme."""

    # Backgrounds - from deepest to most elevated
    BG_DEEPEST = "#0d0d0d"
    BG_BASE = "#121212"
    BG_SURFACE = "#1a1a1a"
    BG_ELEVATED = "#242424"
    BG_CARD = "#2a2a2a"

    # Borders
    BORDER_SUBTLE = "#333333"
    BORDER_NORMAL = "#444444"
    BORDER_STRONG = "#555555"

    # Text
    TEXT_PRIMARY = "#e0e0e0"
    TEXT_SECONDARY = "#888888"
    TEXT_MUTED = "#666666"

    # Accent colors
    ACCENT_BLUE = "#1976d2"
    ACCENT_CYAN = "#00bcd4"

    # Semantic colors
    POSITIVE = "#4caf50"
    NEGATIVE = "#f44336"
    WARNING = "#ff9800"

    # Chart colors
    CHART_BULLISH = "#4caf50"
    CHART_BEARISH = "#f44336"
    CHART_NEUTRAL = "#888888"

    # Additional chart colors for multiple series
    CHART_BLUE = "#2196f3"
    CHART_CYAN = "#00bcd4"
    CHART_PURPLE = "#9c27b0"
    CHART_ORANGE = "#ff9800"


# QSS Stylesheet
STYLESHEET = """
/* ============================================
   Base Widgets
   ============================================ */

QMainWindow, QDialog {
    background-color: #121212;
    color: #e0e0e0;
}

QWidget {
    background-color: transparent;
    color: #e0e0e0;
    font-family: "Segoe UI", "Roboto", "Arial", sans-serif;
    font-size: 12px;
}

/* ============================================
   Tab Widget
   ============================================ */

QTabWidget::pane {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-top: none;
}

QTabBar::tab {
    background-color: #1a1a1a;
    color: #888888;
    padding: 6px 16px;
    border: 1px solid #333333;
    border-bottom: none;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #242424;
    color: #e0e0e0;
    border-top: 2px solid #1976d2;
}

QTabBar::tab:hover:!selected {
    background-color: #242424;
    color: #e0e0e0;
}

/* ============================================
   Buttons
   ============================================ */

QPushButton {
    background-color: #2a2a2a;
    color: #e0e0e0;
    border: 1px solid #444444;
    border-radius: 2px;
    padding: 6px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #333333;
    border-color: #555555;
}

QPushButton:pressed {
    background-color: #1a1a1a;
}

QPushButton:disabled {
    background-color: #1a1a1a;
    color: #666666;
    border-color: #333333;
}

QPushButton:focus {
    border-color: #1976d2;
    outline: none;
}

/* Buy button (green) */
QPushButton[class="buy"], QPushButton#btn_buy {
    background-color: #1b5e20;
    border-color: #2e7d32;
    color: #e0e0e0;
}

QPushButton[class="buy"]:hover, QPushButton#btn_buy:hover {
    background-color: #2e7d32;
}

/* Sell button (red) */
QPushButton[class="sell"], QPushButton#btn_sell {
    background-color: #b71c1c;
    border-color: #c62828;
    color: #e0e0e0;
}

QPushButton[class="sell"]:hover, QPushButton#btn_sell:hover {
    background-color: #c62828;
}

/* Primary action button */
QPushButton[class="primary"], QPushButton#btn_run {
    background-color: #1565c0;
    border-color: #1976d2;
    color: #ffffff;
}

QPushButton[class="primary"]:hover, QPushButton#btn_run:hover {
    background-color: #1976d2;
}

/* ============================================
   Input Fields
   ============================================ */

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 6px 8px;
    selection-background-color: #1976d2;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {
    border-color: #1976d2;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: #0d0d0d;
    color: #666666;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #888888;
    margin-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    selection-background-color: #1976d2;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #242424;
    border: none;
    width: 16px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #333333;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #888888;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #888888;
}

/* ============================================
   Group Box
   ============================================ */

QGroupBox {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 2px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 500;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: #888888;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* ============================================
   Tables
   ============================================ */

QTableWidget, QTableView {
    background-color: #1a1a1a;
    alternate-background-color: #1f1f1f;
    color: #e0e0e0;
    border: 1px solid #333333;
    gridline-color: #333333;
    selection-background-color: #1976d2;
}

QTableWidget::item, QTableView::item {
    padding: 4px 8px;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #1976d2;
}

QHeaderView::section {
    background-color: #242424;
    color: #888888;
    border: none;
    border-right: 1px solid #333333;
    border-bottom: 1px solid #333333;
    padding: 6px 8px;
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 500;
}

QHeaderView::section:hover {
    background-color: #2a2a2a;
}

/* ============================================
   Scroll Bars
   ============================================ */

QScrollBar:vertical {
    background-color: #121212;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #444444;
    border-radius: 4px;
    min-height: 30px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background-color: #121212;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #444444;
    border-radius: 4px;
    min-width: 30px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #555555;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ============================================
   Splitter
   ============================================ */

QSplitter::handle {
    background-color: #333333;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QSplitter::handle:hover {
    background-color: #1976d2;
}

/* ============================================
   Labels
   ============================================ */

QLabel {
    color: #e0e0e0;
    background-color: transparent;
}

QLabel[class="header"] {
    font-size: 14px;
    font-weight: 600;
    color: #e0e0e0;
}

QLabel[class="subheader"] {
    font-size: 11px;
    color: #888888;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QLabel[class="value-positive"] {
    color: #4caf50;
}

QLabel[class="value-negative"] {
    color: #f44336;
}

QLabel[class="value-neutral"] {
    color: #888888;
}

/* ============================================
   Alert Frames
   ============================================ */

QFrame[class="alert-warning"], QFrame#termination_warning {
    background-color: #4a3000;
    border: 2px solid #ff9800;
    border-radius: 4px;
}

QFrame[class="alert-error"] {
    background-color: #4a0000;
    border: 2px solid #f44336;
    border-radius: 4px;
}

QFrame[class="alert-success"] {
    background-color: #1b3d1b;
    border: 2px solid #4caf50;
    border-radius: 4px;
}

QFrame[class="alert-info"] {
    background-color: #0d3d5c;
    border: 2px solid #1976d2;
    border-radius: 4px;
}

/* ============================================
   Progress Bar
   ============================================ */

QProgressBar {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 2px;
    text-align: center;
    color: #e0e0e0;
}

QProgressBar::chunk {
    background-color: #1976d2;
    border-radius: 1px;
}

/* ============================================
   Menu
   ============================================ */

QMenuBar {
    background-color: #121212;
    color: #e0e0e0;
    border-bottom: 1px solid #333333;
}

QMenuBar::item {
    padding: 4px 8px;
}

QMenuBar::item:selected {
    background-color: #242424;
}

QMenu {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
}

QMenu::item {
    padding: 6px 24px;
}

QMenu::item:selected {
    background-color: #1976d2;
}

QMenu::separator {
    height: 1px;
    background-color: #333333;
    margin: 4px 8px;
}

/* ============================================
   Tool Tips
   ============================================ */

QToolTip {
    background-color: #242424;
    color: #e0e0e0;
    border: 1px solid #444444;
    padding: 4px 8px;
}

/* ============================================
   Check Box & Radio Button
   ============================================ */

QCheckBox, QRadioButton {
    color: #e0e0e0;
    spacing: 8px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    background-color: #1a1a1a;
    border: 1px solid #444444;
}

QCheckBox::indicator {
    border-radius: 2px;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #1976d2;
    border-color: #1976d2;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #1976d2;
}

/* ============================================
   Slider
   ============================================ */

QSlider::groove:horizontal {
    background-color: #333333;
    height: 4px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #1976d2;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background-color: #2196f3;
}

/* ============================================
   Status Bar
   ============================================ */

QStatusBar {
    background-color: #0d0d0d;
    color: #888888;
    border-top: 1px solid #333333;
}

QStatusBar::item {
    border: none;
}

/* ============================================
   Scroll Area
   ============================================ */

QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* ============================================
   List Widget
   ============================================ */

QListWidget {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
}

QListWidget::item:selected {
    background-color: #1976d2;
}

QListWidget::item:hover:!selected {
    background-color: #242424;
}

/* ============================================
   Text Edit / Plain Text Edit
   ============================================ */

QTextEdit, QPlainTextEdit {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    selection-background-color: #1976d2;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #1976d2;
}
"""


class ThemeManager:
    """Manages application theming."""

    @staticmethod
    def apply_theme(app: "QApplication") -> None:
        """Apply the trading terminal theme to the application.

        Args:
            app: The QApplication instance
        """
        # Set the stylesheet
        app.setStyleSheet(STYLESHEET)

        # Set application palette as fallback
        ThemeManager._set_application_palette(app)

        # Configure pyqtgraph
        ThemeManager.configure_pyqtgraph()

    @staticmethod
    def configure_pyqtgraph() -> None:
        """Configure pyqtgraph for dark theme."""
        try:
            import pyqtgraph as pg

            pg.setConfigOption("background", Colors.BG_BASE)
            pg.setConfigOption("foreground", Colors.TEXT_SECONDARY)
            pg.setConfigOptions(antialias=True)
        except ImportError:
            pass  # pyqtgraph not installed

    @staticmethod
    def _set_application_palette(app: "QApplication") -> None:
        """Set the application palette for consistent coloring.

        Args:
            app: The QApplication instance
        """
        palette = QtGui.QPalette()

        # Base colors
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(Colors.BG_BASE))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(Colors.TEXT_PRIMARY))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(Colors.BG_SURFACE))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(Colors.BG_ELEVATED))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(Colors.TEXT_PRIMARY))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(Colors.BG_CARD))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(Colors.TEXT_PRIMARY))
        palette.setColor(QtGui.QPalette.BrightText, QtGui.QColor("#ffffff"))

        # Highlight colors
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(Colors.ACCENT_BLUE))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))

        # Disabled colors
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(Colors.TEXT_MUTED))
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(Colors.TEXT_MUTED))
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(Colors.TEXT_MUTED))

        # Link colors
        palette.setColor(QtGui.QPalette.Link, QtGui.QColor(Colors.ACCENT_CYAN))
        palette.setColor(QtGui.QPalette.LinkVisited, QtGui.QColor(Colors.ACCENT_BLUE))

        # Tooltip
        palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(Colors.BG_ELEVATED))
        palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(Colors.TEXT_PRIMARY))

        app.setPalette(palette)

    @staticmethod
    def get_chart_pen(color_type: str, width: int = 2):
        """Get a themed pyqtgraph pen.

        Args:
            color_type: One of 'bullish', 'bearish', 'neutral', 'blue', 'cyan', 'purple', 'orange'
            width: Pen width in pixels

        Returns:
            pyqtgraph pen object
        """
        try:
            import pyqtgraph as pg

            color_map = {
                "bullish": Colors.CHART_BULLISH,
                "bearish": Colors.CHART_BEARISH,
                "neutral": Colors.CHART_NEUTRAL,
                "positive": Colors.POSITIVE,
                "negative": Colors.NEGATIVE,
                "blue": Colors.CHART_BLUE,
                "cyan": Colors.CHART_CYAN,
                "purple": Colors.CHART_PURPLE,
                "orange": Colors.CHART_ORANGE,
                "warning": Colors.WARNING,
                "accent": Colors.ACCENT_BLUE,
            }

            color = color_map.get(color_type, Colors.TEXT_PRIMARY)
            return pg.mkPen(color=color, width=width)
        except ImportError:
            return None

    @staticmethod
    def get_chart_brush(color_type: str, alpha: int = 80):
        """Get a themed pyqtgraph brush for fills.

        Args:
            color_type: One of 'bullish', 'bearish', 'neutral', etc.
            alpha: Alpha transparency (0-255)

        Returns:
            pyqtgraph brush object
        """
        try:
            import pyqtgraph as pg

            color_map = {
                "bullish": Colors.CHART_BULLISH,
                "bearish": Colors.CHART_BEARISH,
                "neutral": Colors.CHART_NEUTRAL,
                "positive": Colors.POSITIVE,
                "negative": Colors.NEGATIVE,
                "blue": Colors.CHART_BLUE,
                "warning": Colors.WARNING,
            }

            hex_color = color_map.get(color_type, Colors.TEXT_PRIMARY)
            # Convert hex to RGB and add alpha
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)

            return pg.mkBrush(r, g, b, alpha)
        except ImportError:
            return None

    @staticmethod
    def style_value_by_sign(label: "QLabel", value: float, include_sign: bool = True, suffix: str = "") -> None:
        """Style a QLabel based on value sign (positive/negative).

        Args:
            label: The QLabel to style
            value: The numeric value
            include_sign: Whether to include +/- sign in text
            suffix: Optional suffix (e.g., '%', '$')
        """
        if value > 0:
            color = Colors.POSITIVE
            sign = "+" if include_sign else ""
        elif value < 0:
            color = Colors.NEGATIVE
            sign = ""  # Negative already has sign
        else:
            color = Colors.TEXT_SECONDARY
            sign = "" if not include_sign else ""

        label.setStyleSheet(f"color: {color};")
        label.setText(f"{sign}{value:.2f}{suffix}")

    @staticmethod
    def style_return_label(label: "QLabel", value: float) -> None:
        """Style a return percentage label.

        Args:
            label: The QLabel to style
            value: The return percentage
        """
        ThemeManager.style_value_by_sign(label, value, include_sign=True, suffix="%")

    @staticmethod
    def style_currency_label(label: "QLabel", value: float, include_sign: bool = False) -> None:
        """Style a currency value label.

        Args:
            label: The QLabel to style
            value: The currency value
            include_sign: Whether to include +/- sign
        """
        if value > 0:
            color = Colors.POSITIVE
            sign = "+$" if include_sign else "$"
        elif value < 0:
            color = Colors.NEGATIVE
            sign = "-$"
            value = abs(value)
        else:
            color = Colors.TEXT_SECONDARY
            sign = "$"

        label.setStyleSheet(f"color: {color};")
        label.setText(f"{sign}{value:,.2f}")

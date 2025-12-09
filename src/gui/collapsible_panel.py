from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets


class CollapsiblePanel(QtWidgets.QWidget):
    """A panel with a header that can be collapsed/expanded.

    Features:
    - Scrollable content area when expanded
    - Fixed minimum height when expanded for consistent sizing
    - Proper size hints for splitter integration
    """

    collapsed_changed = QtCore.pyqtSignal(bool)

    # Height constants
    MIN_EXPANDED_HEIGHT = 80  # Minimum height when expanded
    COLLAPSED_HEIGHT = 28  # Height of just the header

    def __init__(
        self,
        title: str,
        parent: Optional[QtWidgets.QWidget] = None,
        initially_collapsed: bool = False,
    ):
        super().__init__(parent)
        self._title = title
        self._is_collapsed = initially_collapsed
        self._content_widget: Optional[QtWidgets.QWidget] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the collapsible panel layout."""
        self._main_layout = QtWidgets.QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Header button
        self._header = QtWidgets.QToolButton()
        self._header.setStyleSheet("""
            QToolButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                text-align: left;
                font-weight: bold;
                color: #d4d4d4;
            }
            QToolButton:hover {
                background-color: #3d3d3d;
            }
        """)
        self._header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._header.setArrowType(
            QtCore.Qt.DownArrow if not self._is_collapsed else QtCore.Qt.RightArrow
        )
        self._header.setText(self._title)
        self._header.setCheckable(True)
        self._header.setChecked(not self._is_collapsed)
        self._header.setFixedHeight(self.COLLAPSED_HEIGHT)
        self._header.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._header.clicked.connect(self._on_header_clicked)
        self._main_layout.addWidget(self._header)

        # Scroll area for content
        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a4a;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a5a5a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self._main_layout.addWidget(self._scroll_area, 1)

        # Content container inside scroll area
        self._content_container = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 4, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll_area.setWidget(self._content_container)

        # Apply initial collapsed state
        self._apply_collapsed_state()

    def set_content(self, widget: QtWidgets.QWidget) -> None:
        """Set the content widget for this panel."""
        # Remove old content
        if self._content_widget is not None:
            self._content_layout.removeWidget(self._content_widget)
            self._content_widget.setParent(None)

        self._content_widget = widget
        self._content_layout.addWidget(widget)
        self._apply_collapsed_state()

    def _on_header_clicked(self, checked: bool) -> None:
        """Handle header click to toggle collapse state."""
        self._is_collapsed = not checked
        self._header.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self._apply_collapsed_state()
        self.collapsed_changed.emit(self._is_collapsed)

    def _apply_collapsed_state(self) -> None:
        """Apply the current collapsed state to the widget."""
        if self._is_collapsed:
            self._scroll_area.hide()
            self.setFixedHeight(self.COLLAPSED_HEIGHT)
        else:
            self._scroll_area.show()
            self.setMinimumHeight(self.MIN_EXPANDED_HEIGHT)
            self.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX

    def is_collapsed(self) -> bool:
        """Return whether the panel is currently collapsed."""
        return self._is_collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatically set collapse state."""
        if collapsed != self._is_collapsed:
            self._header.click()

    def title(self) -> str:
        """Return the panel title."""
        return self._title

    def set_title(self, title: str) -> None:
        """Set the panel title."""
        self._title = title
        self._header.setText(title)

    def sizeHint(self) -> QtCore.QSize:
        """Return the recommended size for this widget."""
        if self._is_collapsed:
            return QtCore.QSize(200, self.COLLAPSED_HEIGHT)
        return QtCore.QSize(200, 150)

    def minimumSizeHint(self) -> QtCore.QSize:
        """Return the minimum recommended size."""
        if self._is_collapsed:
            return QtCore.QSize(100, self.COLLAPSED_HEIGHT)
        return QtCore.QSize(100, self.MIN_EXPANDED_HEIGHT)

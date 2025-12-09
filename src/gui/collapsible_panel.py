from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets


class CollapsiblePanel(QtWidgets.QWidget):
    """A panel with a header that can be collapsed/expanded."""

    collapsed_changed = QtCore.pyqtSignal(bool)

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
        self._header.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._header.clicked.connect(self._on_header_clicked)
        self._main_layout.addWidget(self._header)

        # Content area (will hold the actual content widget)
        self._content_area = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content_area)
        self._content_layout.setContentsMargins(0, 4, 0, 0)
        self._content_layout.setSpacing(0)
        self._main_layout.addWidget(self._content_area)

        if self._is_collapsed:
            self._content_area.setMaximumHeight(0)

    def set_content(self, widget: QtWidgets.QWidget) -> None:
        """Set the content widget for this panel."""
        # Remove old content
        if self._content_widget is not None:
            self._content_layout.removeWidget(self._content_widget)
            self._content_widget.setParent(None)

        self._content_widget = widget
        self._content_layout.addWidget(widget)

        if self._is_collapsed:
            self._content_area.setMaximumHeight(0)
        else:
            self._content_area.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX

    def _on_header_clicked(self, checked: bool) -> None:
        """Handle header click to toggle collapse state."""
        self._is_collapsed = not checked
        self._header.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

        if self._is_collapsed:
            self._content_area.setMaximumHeight(0)
        else:
            self._content_area.setMaximumHeight(16777215)

        self.collapsed_changed.emit(self._is_collapsed)

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

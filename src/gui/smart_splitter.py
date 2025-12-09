"""SmartSplitter that properly handles CollapsiblePanel widgets.

This splitter respects the collapsed state of CollapsiblePanel children,
preventing collapsed panels from being resized and maintaining proper
space distribution.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.gui.collapsible_panel import CollapsiblePanel


class SmartSplitterHandle(QtWidgets.QSplitterHandle):
    """Custom handle with visual feedback."""

    def __init__(self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QSplitter):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._hovered = False

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        if self._hovered:
            painter.fillRect(self.rect(), QtGui.QColor("#4a90d9"))
        else:
            painter.fillRect(self.rect(), QtGui.QColor("#3d3d3d"))


class SmartSplitter(QtWidgets.QSplitter):
    """A splitter that respects CollapsiblePanel collapsed states.

    When a CollapsiblePanel is collapsed, this splitter:
    - Fixes the collapsed panel to its header height
    - Redistributes space among expanded panels
    - Prevents resize handles from affecting collapsed panels
    """

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Vertical,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(orientation, parent)
        self.setHandleWidth(4)
        self.setChildrenCollapsible(False)
        self._panels: List[CollapsiblePanel] = []

    def createHandle(self) -> QtWidgets.QSplitterHandle:
        """Create a custom handle with visual feedback."""
        return SmartSplitterHandle(self.orientation(), self)

    def addCollapsiblePanel(self, panel: CollapsiblePanel) -> None:
        """Add a CollapsiblePanel and connect its signals."""
        self.addWidget(panel)
        self._panels.append(panel)
        panel.collapsed_changed.connect(self._on_panel_collapsed_changed)
        self._update_panel_constraints()

    def _on_panel_collapsed_changed(self, collapsed: bool) -> None:
        """Handle a panel being collapsed or expanded."""
        self._update_panel_constraints()
        self._redistribute_space()

    def _update_panel_constraints(self) -> None:
        """Update size constraints for all panels."""
        for i, panel in enumerate(self._panels):
            if panel.is_collapsed():
                # Collapsed: fix to header height
                height = CollapsiblePanel.COLLAPSED_HEIGHT
                panel.setFixedHeight(height)
            else:
                # Expanded: allow resizing with minimum
                panel.setMinimumHeight(CollapsiblePanel.MIN_EXPANDED_HEIGHT)
                panel.setMaximumHeight(16777215)

    def _redistribute_space(self) -> None:
        """Redistribute space when panels collapse/expand."""
        sizes = self.sizes()
        if not sizes:
            return

        # Calculate total space and space used by collapsed panels
        total = sum(sizes)
        collapsed_total = 0
        expanded_count = 0

        for i, panel in enumerate(self._panels):
            if panel.is_collapsed():
                collapsed_total += CollapsiblePanel.COLLAPSED_HEIGHT
            else:
                expanded_count += 1

        # Remaining space for expanded panels
        if expanded_count > 0:
            available = total - collapsed_total
            per_expanded = max(
                CollapsiblePanel.MIN_EXPANDED_HEIGHT,
                available // expanded_count
            )

            new_sizes = []
            for i, panel in enumerate(self._panels):
                if panel.is_collapsed():
                    new_sizes.append(CollapsiblePanel.COLLAPSED_HEIGHT)
                else:
                    new_sizes.append(per_expanded)

            # Handle any remaining panels (spacer, etc.)
            for i in range(len(self._panels), self.count()):
                if i < len(sizes):
                    new_sizes.append(sizes[i])

            self.setSizes(new_sizes)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """Handle resize and maintain collapsed panel sizes."""
        super().resizeEvent(event)
        self._update_panel_constraints()

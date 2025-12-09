"""Unit tests for CollapsiblePanel and SmartSplitter."""

import pytest
from PyQt5 import QtCore, QtWidgets

from src.gui.collapsible_panel import CollapsiblePanel
from src.gui.smart_splitter import SmartSplitter


@pytest.fixture
def app(qtbot):
    """Ensure QApplication exists."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TestCollapsiblePanel:
    """Tests for CollapsiblePanel widget."""

    def test_initial_expanded_state(self, qtbot):
        """Panel starts expanded by default."""
        panel = CollapsiblePanel("Test Panel")
        qtbot.addWidget(panel)
        assert panel.is_collapsed() is False

    def test_initial_collapsed_state(self, qtbot):
        """Panel can start collapsed."""
        panel = CollapsiblePanel("Test Panel", initially_collapsed=True)
        qtbot.addWidget(panel)
        assert panel.is_collapsed() is True

    def test_title_getter(self, qtbot):
        """title() returns the panel title."""
        panel = CollapsiblePanel("My Title")
        qtbot.addWidget(panel)
        assert panel.title() == "My Title"

    def test_title_setter(self, qtbot):
        """set_title() updates the panel title."""
        panel = CollapsiblePanel("Initial")
        qtbot.addWidget(panel)
        panel.set_title("Updated")
        assert panel.title() == "Updated"

    def test_set_collapsed_programmatically(self, qtbot):
        """set_collapsed() changes state."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        panel.set_collapsed(True)
        assert panel.is_collapsed() is True

        panel.set_collapsed(False)
        assert panel.is_collapsed() is False

    def test_set_collapsed_no_op_if_same(self, qtbot):
        """set_collapsed() is no-op if state unchanged."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        # Already expanded, setting to expanded should be no-op
        panel.set_collapsed(False)
        assert panel.is_collapsed() is False

    def test_collapsed_changed_signal(self, qtbot):
        """Signal emitted when collapsed state changes."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        signal_received = []
        panel.collapsed_changed.connect(lambda v: signal_received.append(v))

        panel.set_collapsed(True)
        assert signal_received == [True]

        panel.set_collapsed(False)
        assert signal_received == [True, False]

    def test_set_content(self, qtbot):
        """set_content() adds widget to panel."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        content = QtWidgets.QLabel("Content")
        panel.set_content(content)

        assert panel._content_widget is content

    def test_replace_content(self, qtbot):
        """set_content() replaces existing content."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        content1 = QtWidgets.QLabel("Content 1")
        content2 = QtWidgets.QLabel("Content 2")

        panel.set_content(content1)
        panel.set_content(content2)

        assert panel._content_widget is content2

    def test_collapsed_height(self, qtbot):
        """Collapsed panel has fixed height."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        panel.set_collapsed(True)
        # Should be fixed to COLLAPSED_HEIGHT
        assert panel.maximumHeight() == CollapsiblePanel.COLLAPSED_HEIGHT
        assert panel.minimumHeight() == CollapsiblePanel.COLLAPSED_HEIGHT

    def test_expanded_minimum_height(self, qtbot):
        """Expanded panel has minimum height."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        panel.set_collapsed(False)
        assert panel.minimumHeight() >= CollapsiblePanel.MIN_EXPANDED_HEIGHT

    def test_size_hint_collapsed(self, qtbot):
        """sizeHint returns appropriate size when collapsed."""
        panel = CollapsiblePanel("Test", initially_collapsed=True)
        qtbot.addWidget(panel)

        hint = panel.sizeHint()
        assert hint.height() == CollapsiblePanel.COLLAPSED_HEIGHT

    def test_size_hint_expanded(self, qtbot):
        """sizeHint returns larger size when expanded."""
        panel = CollapsiblePanel("Test", initially_collapsed=False)
        qtbot.addWidget(panel)

        hint = panel.sizeHint()
        assert hint.height() > CollapsiblePanel.COLLAPSED_HEIGHT

    def test_scroll_area_hidden_when_collapsed(self, qtbot):
        """Scroll area is hidden when collapsed."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)

        panel.set_collapsed(True)
        assert panel._scroll_area.isHidden() is True

    def test_scroll_area_visible_when_expanded(self, qtbot):
        """Scroll area is visible when expanded."""
        panel = CollapsiblePanel("Test")
        qtbot.addWidget(panel)
        panel.show()

        panel.set_collapsed(False)
        assert panel._scroll_area.isHidden() is False


class TestSmartSplitter:
    """Tests for SmartSplitter widget."""

    def test_creates_vertical_splitter(self, qtbot):
        """SmartSplitter creates vertical splitter by default."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)
        assert splitter.orientation() == QtCore.Qt.Vertical

    def test_creates_horizontal_splitter(self, qtbot):
        """SmartSplitter can create horizontal splitter."""
        splitter = SmartSplitter(QtCore.Qt.Horizontal)
        qtbot.addWidget(splitter)
        assert splitter.orientation() == QtCore.Qt.Horizontal

    def test_add_collapsible_panel(self, qtbot):
        """addCollapsiblePanel adds panel to splitter."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel = CollapsiblePanel("Test")
        splitter.addCollapsiblePanel(panel)

        assert splitter.count() == 1
        assert len(splitter._panels) == 1

    def test_add_multiple_panels(self, qtbot):
        """Multiple panels can be added."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel1 = CollapsiblePanel("Panel 1")
        panel2 = CollapsiblePanel("Panel 2")
        panel3 = CollapsiblePanel("Panel 3")

        splitter.addCollapsiblePanel(panel1)
        splitter.addCollapsiblePanel(panel2)
        splitter.addCollapsiblePanel(panel3)

        assert splitter.count() == 3
        assert len(splitter._panels) == 3

    def test_collapsed_panel_fixed_height(self, qtbot):
        """Collapsed panels have fixed height in splitter."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel = CollapsiblePanel("Test")
        splitter.addCollapsiblePanel(panel)

        panel.set_collapsed(True)
        # Panel should be fixed to collapsed height
        assert panel.maximumHeight() == CollapsiblePanel.COLLAPSED_HEIGHT

    def test_expanded_panel_resizable(self, qtbot):
        """Expanded panels are resizable."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel = CollapsiblePanel("Test")
        splitter.addCollapsiblePanel(panel)

        panel.set_collapsed(False)
        # Panel should have large max height (resizable)
        assert panel.maximumHeight() > CollapsiblePanel.MIN_EXPANDED_HEIGHT

    def test_children_not_collapsible(self, qtbot):
        """SmartSplitter prevents Qt's internal collapsing."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)
        assert splitter.childrenCollapsible() is False

    def test_custom_handle_created(self, qtbot):
        """SmartSplitter creates custom handles."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel1 = CollapsiblePanel("Panel 1")
        panel2 = CollapsiblePanel("Panel 2")
        splitter.addCollapsiblePanel(panel1)
        splitter.addCollapsiblePanel(panel2)

        # Handle at index 1 should be our custom handle
        handle = splitter.handle(1)
        assert handle is not None


class TestSmartSplitterWithMixedPanels:
    """Tests for SmartSplitter with regular widgets too."""

    def test_add_regular_widget(self, qtbot):
        """Regular widgets can be added with addWidget."""
        splitter = SmartSplitter()
        qtbot.addWidget(splitter)

        panel = CollapsiblePanel("Test")
        spacer = QtWidgets.QWidget()

        splitter.addCollapsiblePanel(panel)
        splitter.addWidget(spacer)

        assert splitter.count() == 2
        assert len(splitter._panels) == 1  # Only tracks collapsible panels

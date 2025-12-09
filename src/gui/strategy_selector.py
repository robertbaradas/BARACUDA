from __future__ import annotations

from typing import Dict, Optional

from PyQt5 import QtCore, QtWidgets

from src.strategies import get_available_strategies


class StrategySelectorBar(QtWidgets.QWidget):
    """Horizontal bar of buttons for selecting strategies."""

    strategySelected = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._buttons: Dict[str, QtWidgets.QPushButton] = {}
        self._current_strategy: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build button bar from available strategies."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QtWidgets.QLabel("Strategy:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        for name in get_available_strategies():
            btn = QtWidgets.QPushButton(name)
            btn.setCheckable(True)
            btn.setMinimumWidth(60)
            btn.clicked.connect(lambda checked, n=name: self._on_button_clicked(n))
            self._buttons[name] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Select first strategy by default
        strategies = get_available_strategies()
        if strategies:
            self.select_strategy(strategies[0])

    def _on_button_clicked(self, name: str) -> None:
        """Handle strategy button click."""
        self.select_strategy(name)
        self.strategySelected.emit(name)

    def select_strategy(self, name: str) -> None:
        """Select a strategy and update button states."""
        self._current_strategy = name
        for btn_name, btn in self._buttons.items():
            btn.setChecked(btn_name == name)
            if btn_name == name:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1976d2;
                        color: white;
                        font-weight: bold;
                        border-radius: 4px;
                        padding: 6px 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #424242;
                        color: #d4d4d4;
                        border-radius: 4px;
                        padding: 6px 12px;
                    }
                    QPushButton:hover {
                        background-color: #616161;
                    }
                """)

    def get_current_strategy(self) -> Optional[str]:
        """Return currently selected strategy name."""
        return self._current_strategy

    def refresh(self) -> None:
        """Refresh button list from registry (call after adding new strategies)."""
        # Clear existing buttons
        for btn in self._buttons.values():
            btn.deleteLater()
        self._buttons.clear()

        # Rebuild
        layout = self.layout()
        for name in get_available_strategies():
            btn = QtWidgets.QPushButton(name)
            btn.setCheckable(True)
            btn.setMinimumWidth(60)
            btn.clicked.connect(lambda checked, n=name: self._on_button_clicked(n))
            self._buttons[name] = btn
            layout.insertWidget(layout.count() - 1, btn)  # Before stretch

        # Reselect current or first
        if self._current_strategy and self._current_strategy in self._buttons:
            self.select_strategy(self._current_strategy)
        elif self._buttons:
            self.select_strategy(list(self._buttons.keys())[0])

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5 import QtCore, QtWidgets

from src.strategies import get_available_strategies, create_strategy
from src.strategies.ensemble_strategy import VotingMode


class EnsemblePanel(QtWidgets.QGroupBox):
    """Panel for configuring ensemble strategy settings."""

    ensembleChanged = QtCore.pyqtSignal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("Ensemble Configuration", parent)
        self._strategy_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self._weight_spinboxes: Dict[str, QtWidgets.QDoubleSpinBox] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the ensemble configuration UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # Enable ensemble checkbox
        self.chk_enable = QtWidgets.QCheckBox("Enable Ensemble Mode")
        self.chk_enable.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self.chk_enable)

        # Strategy selection
        strategies_group = QtWidgets.QGroupBox("Select Strategies")
        strategies_layout = QtWidgets.QGridLayout()

        row = 0
        for name in get_available_strategies():
            chk = QtWidgets.QCheckBox(name)
            chk.stateChanged.connect(self._on_strategy_changed)
            self._strategy_checkboxes[name] = chk
            strategies_layout.addWidget(chk, row, 0)

            # Weight spinbox
            weight_label = QtWidgets.QLabel("Weight:")
            weight_spin = QtWidgets.QDoubleSpinBox()
            weight_spin.setRange(0.1, 10.0)
            weight_spin.setValue(1.0)
            weight_spin.setSingleStep(0.1)
            weight_spin.setEnabled(False)
            weight_spin.valueChanged.connect(self._on_weight_changed)
            self._weight_spinboxes[name] = weight_spin

            strategies_layout.addWidget(weight_label, row, 1)
            strategies_layout.addWidget(weight_spin, row, 2)
            row += 1

        strategies_group.setLayout(strategies_layout)
        layout.addWidget(strategies_group)

        # Voting mode
        voting_layout = QtWidgets.QHBoxLayout()
        voting_layout.addWidget(QtWidgets.QLabel("Voting Mode:"))

        self.combo_voting = QtWidgets.QComboBox()
        self.combo_voting.addItems([
            "Unanimous (all agree)",
            "Majority (>50% agree)",
            "Weighted (sum > threshold)",
            "Any (first signal wins)",
        ])
        self.combo_voting.setCurrentIndex(1)  # Default to majority
        self.combo_voting.currentIndexChanged.connect(self._on_voting_changed)
        voting_layout.addWidget(self.combo_voting)
        layout.addLayout(voting_layout)

        # Threshold
        threshold_layout = QtWidgets.QHBoxLayout()
        threshold_layout.addWidget(QtWidgets.QLabel("Threshold:"))

        self.spin_threshold = QtWidgets.QDoubleSpinBox()
        self.spin_threshold.setRange(0.0, 1.0)
        self.spin_threshold.setValue(0.5)
        self.spin_threshold.setSingleStep(0.1)
        self.spin_threshold.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.spin_threshold)
        layout.addLayout(threshold_layout)

        # Initially disabled
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        """Enable or disable ensemble controls."""
        for chk in self._strategy_checkboxes.values():
            chk.setEnabled(enabled)
        self.combo_voting.setEnabled(enabled)
        self.spin_threshold.setEnabled(enabled)
        self._update_weight_states()

    def _update_weight_states(self) -> None:
        """Enable weight spinboxes only for checked strategies."""
        ensemble_enabled = self.chk_enable.isChecked()
        for name, chk in self._strategy_checkboxes.items():
            spin = self._weight_spinboxes[name]
            spin.setEnabled(ensemble_enabled and chk.isChecked())

    def _on_enable_changed(self, state: int) -> None:
        """Handle ensemble enable checkbox change."""
        self._set_enabled(state == QtCore.Qt.Checked)
        self.ensembleChanged.emit()

    def _on_strategy_changed(self, state: int) -> None:
        """Handle strategy checkbox change."""
        self._update_weight_states()
        self.ensembleChanged.emit()

    def _on_voting_changed(self, index: int) -> None:
        """Handle voting mode change."""
        self.ensembleChanged.emit()

    def _on_threshold_changed(self, value: float) -> None:
        """Handle threshold change."""
        self.ensembleChanged.emit()

    def _on_weight_changed(self, value: float) -> None:
        """Handle weight change."""
        self.ensembleChanged.emit()

    def is_ensemble_enabled(self) -> bool:
        """Check if ensemble mode is enabled."""
        return self.chk_enable.isChecked()

    def get_selected_strategies(self) -> List[str]:
        """Get list of selected strategy names."""
        return [
            name for name, chk in self._strategy_checkboxes.items()
            if chk.isChecked()
        ]

    def get_weights(self) -> Dict[str, float]:
        """Get weight for each selected strategy."""
        return {
            name: self._weight_spinboxes[name].value()
            for name in self.get_selected_strategies()
        }

    def get_voting_mode(self) -> VotingMode:
        """Get selected voting mode."""
        index = self.combo_voting.currentIndex()
        modes = [VotingMode.UNANIMOUS, VotingMode.MAJORITY, VotingMode.WEIGHTED, VotingMode.ANY]
        return modes[index]

    def get_threshold(self) -> float:
        """Get voting threshold."""
        return self.spin_threshold.value()

    def refresh_strategies(self) -> None:
        """Refresh strategy list from registry."""
        # Add any new strategies
        for name in get_available_strategies():
            if name not in self._strategy_checkboxes:
                # Would need to rebuild UI - for now just skip
                pass

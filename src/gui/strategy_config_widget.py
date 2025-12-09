from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5 import QtCore, QtWidgets

from src.strategies import BaseStrategy, StrategyParameter


class StrategyConfigWidget(QtWidgets.QGroupBox):
    """Dynamically generated configuration widget for any strategy."""

    parametersChanged = QtCore.pyqtSignal(dict)

    def __init__(
        self,
        strategy: BaseStrategy,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(strategy.display_name, parent)
        self.strategy = strategy
        self._controls: Dict[str, QtWidgets.QWidget] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build UI controls from strategy parameters."""
        layout = QtWidgets.QFormLayout(self)

        for param in self.strategy.get_parameters():
            widget = self._create_control(param)
            self._controls[param.name] = widget

            # Add tooltip
            if param.description:
                widget.setToolTip(param.description)

            layout.addRow(f"{param.label}:", widget)

    def _create_control(self, param: StrategyParameter) -> QtWidgets.QWidget:
        """Create appropriate control widget for parameter type."""
        if param.param_type == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(
                int(param.min_value) if param.min_value is not None else -999999,
                int(param.max_value) if param.max_value is not None else 999999,
            )
            widget.setValue(int(param.default))
            widget.valueChanged.connect(self._on_value_changed)
            return widget

        elif param.param_type == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setRange(
                param.min_value if param.min_value is not None else -999999.0,
                param.max_value if param.max_value is not None else 999999.0,
            )
            widget.setValue(float(param.default))
            widget.setDecimals(2)
            widget.setSingleStep(0.1)
            widget.valueChanged.connect(self._on_value_changed)
            return widget

        elif param.param_type == "choice":
            widget = QtWidgets.QComboBox()
            if param.choices:
                widget.addItems([str(c) for c in param.choices])
                if param.default in param.choices:
                    widget.setCurrentText(str(param.default))
            widget.currentTextChanged.connect(self._on_value_changed)
            return widget

        else:
            # Fallback to line edit
            widget = QtWidgets.QLineEdit()
            widget.setText(str(param.default))
            widget.textChanged.connect(self._on_value_changed)
            return widget

    def _on_value_changed(self) -> None:
        """Emit signal when any parameter changes."""
        self.parametersChanged.emit(self.get_parameters())

    def get_parameters(self) -> Dict[str, Any]:
        """Get current parameter values from all controls."""
        params = {}
        for param in self.strategy.get_parameters():
            widget = self._controls.get(param.name)
            if widget is None:
                continue

            if isinstance(widget, QtWidgets.QSpinBox):
                params[param.name] = widget.value()
            elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                params[param.name] = widget.value()
            elif isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentText()
                # Try to convert back to original type if it was in choices
                if param.choices and param.default is not None:
                    if isinstance(param.default, bool):
                        params[param.name] = value.lower() == "true"
                    elif isinstance(param.default, int):
                        try:
                            params[param.name] = int(value)
                        except ValueError:
                            params[param.name] = value
                    elif isinstance(param.default, float):
                        try:
                            params[param.name] = float(value)
                        except ValueError:
                            params[param.name] = value
                    else:
                        params[param.name] = value
                else:
                    params[param.name] = value
            elif isinstance(widget, QtWidgets.QLineEdit):
                params[param.name] = widget.text()

        return params

    def set_parameters(self, params: Dict[str, Any]) -> None:
        """Set control values from parameter dictionary."""
        for name, value in params.items():
            widget = self._controls.get(name)
            if widget is None:
                continue

            # Block signals to prevent triggering parametersChanged
            widget.blockSignals(True)

            if isinstance(widget, QtWidgets.QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QtWidgets.QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(str(value))

            widget.blockSignals(False)

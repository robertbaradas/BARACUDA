"""Unit tests for dynamic strategy configuration widget."""

import pytest
from unittest.mock import Mock, MagicMock
from PyQt5 import QtWidgets

from src.strategies import create_strategy
from src.strategies.base_strategy import StrategyParameter


class TestStrategyConfigWidget:
    """Tests for StrategyConfigWidget."""

    @pytest.fixture
    def app(self, qtbot):
        """Ensure QApplication exists."""
        return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @pytest.fixture
    def rsi_strategy(self):
        """Create RSI strategy instance."""
        return create_strategy("RSI")

    def test_creates_controls_for_all_parameters(self, qtbot, rsi_strategy):
        """Widget creates a control for each strategy parameter."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        params = rsi_strategy.get_parameters()
        assert len(widget._controls) == len(params)

        for param in params:
            assert param.name in widget._controls

    def test_int_parameter_creates_spinbox(self, qtbot, rsi_strategy):
        """Integer parameters create QSpinBox."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        # RSI period is an int parameter
        period_control = widget._controls.get("period")
        assert isinstance(period_control, QtWidgets.QSpinBox)
        assert period_control.value() == 14  # default

    def test_choice_parameter_creates_combobox(self, qtbot, rsi_strategy):
        """Choice parameters create QComboBox."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        # middle_behavior is a choice parameter
        middle_control = widget._controls.get("middle_behavior")
        assert isinstance(middle_control, QtWidgets.QComboBox)

    def test_get_parameters_returns_current_values(self, qtbot, rsi_strategy):
        """get_parameters returns dict of current control values."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        params = widget.get_parameters()
        assert params["period"] == 14
        assert params["oversold"] == 30
        assert params["overbought"] == 70
        assert params["middle_behavior"] == "hold"

    def test_set_parameters_updates_controls(self, qtbot, rsi_strategy):
        """set_parameters updates control values."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        widget.set_parameters({"period": 21, "oversold": 25})

        assert widget._controls["period"].value() == 21
        assert widget._controls["oversold"].value() == 25

    def test_parameters_changed_signal_emitted(self, qtbot, rsi_strategy):
        """parametersChanged signal emitted when control value changes."""
        from src.gui.strategy_config_widget import StrategyConfigWidget

        widget = StrategyConfigWidget(rsi_strategy)
        qtbot.addWidget(widget)

        with qtbot.waitSignal(widget.parametersChanged, timeout=1000):
            widget._controls["period"].setValue(21)

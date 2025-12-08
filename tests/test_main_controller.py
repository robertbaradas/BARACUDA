"""Example tests demonstrating dependency injection with mocks."""

import pytest
from unittest.mock import Mock, MagicMock

from src.controllers.main_controller import MainController
from src.data_models import Account


class TestMainController:
    """Tests for MainController using dependency injection."""

    def test_run_auth_flow_success(self):
        """Test successful authentication flow."""
        # Arrange
        mock_parent = Mock()
        mock_session = Mock()
        mock_session.user = Mock()
        mock_session.user.id = "user-123"

        mock_auth_dialog = Mock()
        mock_auth_dialog.exec_.return_value = mock_session

        controller = MainController(
            parent_widget=mock_parent,
            auth_dialog_factory=lambda: mock_auth_dialog,
        )

        # Act
        result = controller.run_auth_flow()

        # Assert
        assert result is True
        assert controller.user_id == "user-123"
        assert controller.session == mock_session

    def test_run_auth_flow_cancelled(self, monkeypatch):
        """Test authentication flow when user cancels."""
        # Arrange
        mock_parent = Mock()
        mock_auth_dialog = Mock()
        mock_auth_dialog.exec_.return_value = None  # User cancelled

        # Mock QMessageBox.critical to avoid Qt widget requirement
        mock_critical = Mock()
        monkeypatch.setattr("src.controllers.main_controller.QtWidgets.QMessageBox.critical", mock_critical)

        controller = MainController(
            parent_widget=mock_parent,
            auth_dialog_factory=lambda: mock_auth_dialog,
        )

        # Act
        result = controller.run_auth_flow()

        # Assert
        assert result is False
        mock_critical.assert_called_once()

    def test_initialize_account(self):
        """Test account initialization with mocked service."""
        # Arrange
        mock_parent = Mock()
        mock_account = Account(
            id="acc-123",
            user_id="user-123",
            name="Paper-1",
            starting_cash=10000.0,
        )

        mock_account_service = Mock()
        mock_account_service.get_or_create_account.return_value = mock_account

        controller = MainController(
            parent_widget=mock_parent,
            account_service_factory=lambda uid: mock_account_service,
        )
        controller.user_id = "user-123"

        # Act
        result = controller.initialize_account()

        # Assert
        assert result == mock_account
        mock_account_service.initialize_schema.assert_called_once()
        mock_account_service.get_or_create_account.assert_called_once()

    def test_shutdown_calls_sign_out(self):
        """Test that shutdown calls sign_out function."""
        # Arrange
        mock_parent = Mock()
        mock_sign_out = Mock()

        controller = MainController(
            parent_widget=mock_parent,
            sign_out_fn=mock_sign_out,
        )

        # Act
        controller.shutdown()

        # Assert
        mock_sign_out.assert_called_once()

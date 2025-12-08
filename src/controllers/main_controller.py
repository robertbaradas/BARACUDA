from __future__ import annotations

import sys
import logging
from typing import Optional, Any, Callable

from PyQt5 import QtWidgets

from src.auth_client import sign_out
from src.gui_auth import AuthDialog
from src.services.account_service import AccountService
from src.data_models import Account

logger = logging.getLogger(__name__)


class MainController:
    """Orchestrates application initialization and authentication flow."""

    def __init__(
        self,
        parent_widget: QtWidgets.QWidget,
        auth_dialog_factory: Optional[Callable[[], Any]] = None,
        account_service_factory: Optional[Callable[[str], AccountService]] = None,
        sign_out_fn: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent_widget
        self.session: Optional[Any] = None
        self.user_id: Optional[str] = None
        self.account_service: Optional[AccountService] = None
        self.active_account: Optional[Account] = None

        # Dependency injection with defaults
        self._auth_dialog_factory = auth_dialog_factory or (lambda: AuthDialog(self.parent))
        self._account_service_factory = account_service_factory or AccountService
        self._sign_out_fn = sign_out_fn or sign_out

    def run_auth_flow(self) -> bool:
        """Execute authentication dialog flow.

        Returns:
            True if authentication successful, False otherwise
        """
        auth_dialog = self._auth_dialog_factory()
        session = auth_dialog.exec_()

        if not session:
            QtWidgets.QMessageBox.critical(
                self.parent,
                "Authentication Required",
                "You must log in to use this application.",
            )
            return False

        self.session = session
        self.user_id = self._resolve_user_id(session)

        if not self.user_id:
            QtWidgets.QMessageBox.critical(
                self.parent,
                "Authentication Error",
                "Unable to determine Supabase user id.",
            )
            return False

        return True

    def initialize_account(self) -> Account:
        """Initialize account service and load/create account.

        Returns:
            The active account
        """
        self.account_service = self._account_service_factory(self.user_id)
        self.account_service.initialize_schema()
        self.active_account = self.account_service.get_or_create_account()
        return self.active_account

    def shutdown(self) -> None:
        """Clean up on application close."""
        try:
            self._sign_out_fn()
        except Exception as exc:
            logger.debug("Sign out failed: %s", exc)

    def _resolve_user_id(self, session: Any) -> Optional[str]:
        """Extract user ID from session object."""
        user = getattr(session, "user", None)
        if user is None and isinstance(session, dict):
            user = session.get("user")
        if user is None:
            return None
        user_id = getattr(user, "id", None)
        if user_id is None and isinstance(user, dict):
            user_id = user.get("id")
        return user_id

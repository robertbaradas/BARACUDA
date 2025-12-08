from __future__ import annotations

import re
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from src.auth_client import AuthError, sign_in, sign_up


class AuthDialog(QtWidgets.QDialog):
    """Modal dialog for login/sign-up flows."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Authentication Required")
        self._session = None
        self._user_id: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._build_login_tab(), "Login")
        self.tabs.addTab(self._build_signup_tab(), "Sign Up")
        layout.addWidget(self.tabs)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: red;")
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

    def _build_login_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        self.login_email = QtWidgets.QLineEdit()
        self.login_email.setPlaceholderText("Email or username")
        self.login_password = QtWidgets.QLineEdit()
        self.login_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.btn_login = QtWidgets.QPushButton("Login")
        self.btn_login.clicked.connect(self._handle_login)
        form.addRow("Email / Username", self.login_email)
        form.addRow("Password", self.login_password)
        form.addRow("", self.btn_login)
        return widget

    def _build_signup_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        self.signup_email = QtWidgets.QLineEdit()
        self.signup_username = QtWidgets.QLineEdit()
        self.signup_password = QtWidgets.QLineEdit()
        self.signup_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.signup_confirm = QtWidgets.QLineEdit()
        self.signup_confirm.setEchoMode(QtWidgets.QLineEdit.Password)
        self.btn_signup = QtWidgets.QPushButton("Sign Up")
        self.btn_signup.clicked.connect(self._handle_signup)
        form.addRow("Email", self.signup_email)
        form.addRow("Username", self.signup_username)
        form.addRow("Password", self.signup_password)
        form.addRow("Confirm", self.signup_confirm)
        form.addRow("", self.btn_signup)
        return widget

    def exec_(self) -> Optional[object]:  # noqa: D401 - Qt signature
        """Execute dialog and return session on success."""
        result = super().exec_()
        return self._session if result == QtWidgets.QDialog.Accepted else None

    def _handle_login(self) -> None:
        email = self.login_email.text().strip()
        password = self.login_password.text()
        if not self._validate_credentials(email, password):
            return
        self._set_status("")
        self._set_buttons_enabled(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            session, _ = sign_in(email, password)
            self._session = session
            self.accept()
        except AuthError as exc:
            self._set_status(str(exc))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._set_buttons_enabled(True)

    def _handle_signup(self) -> None:
        email = self.signup_email.text().strip()
        username = self.signup_username.text().strip()
        password = self.signup_password.text()
        confirm = self.signup_confirm.text()
        if not self._validate_email(email):
            self._set_status("Invalid email address.")
            return
        if len(username) < 3:
            self._set_status("Username must be at least 3 characters.")
            return
        if len(password) < 8:
            self._set_status("Password must be at least 8 characters.")
            return
        if password != confirm:
            self._set_status("Passwords do not match.")
            return
        self._set_status("")
        self._set_buttons_enabled(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            session, _ = sign_up(email, password, username)
            self._session = session
            self.accept()
        except AuthError as exc:
            self._set_status(str(exc))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._set_buttons_enabled(True)

    def _validate_credentials(self, email: str, password: str) -> bool:
        if not email:
            self._set_status("Enter email or username.")
            return False
        if len(password) < 8:
            self._set_status("Password must be at least 8 characters.")
            return False
        return True

    @staticmethod
    def _validate_email(email: str) -> bool:
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.btn_login.setEnabled(enabled)
        self.btn_signup.setEnabled(enabled)

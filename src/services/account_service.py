from __future__ import annotations

import logging
from typing import List, Optional

import config
from src.data_models import Account
from src.supabase_store import (
    SupabaseStoreError,
    create_default_account,
    ensure_schema,
    load_accounts,
)

logger = logging.getLogger(__name__)


class AccountService:
    """Service layer for account management operations."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._active_account: Optional[Account] = None

    def initialize_schema(self) -> None:
        """Ensure database schema exists."""
        ensure_schema()

    def get_or_create_account(self) -> Account:
        """Load existing account or create a default one.

        Returns:
            The user's active account

        Raises:
            RuntimeError: If account cannot be loaded or created
        """
        try:
            accounts = load_accounts(self.user_id)
        except SupabaseStoreError as exc:
            logger.warning("Unable to load accounts: %s", exc)
            accounts = []

        if accounts:
            self._active_account = accounts[0]
        else:
            self._active_account = create_default_account(
                self.user_id,
                name="Paper-1",
                starting_cash=config.STARTING_CAPITAL,
            )

        return self._active_account

    @property
    def active_account(self) -> Optional[Account]:
        """Get the currently active account."""
        return self._active_account

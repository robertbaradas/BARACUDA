from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from supabase import Client, create_client

import config

logger = logging.getLogger(__name__)

Session = Any

_SESSION_FILE = Path(os.path.expanduser("~/.stock_viewer_session"))
_client: Optional[Client] = None
_active_session: Optional[Session] = None
_session_tokens: Optional[Tuple[str, str]] = None
_svc_client: Optional[Client] = None


class AuthError(RuntimeError):
    """Raised when authentication operations fail."""


def _ensure_client() -> Client:
    global _client
    if not config.SUPABASE_URL or "YOUR_SUPABASE" in config.SUPABASE_URL:
        raise AuthError("Supabase URL is not configured.")
    if not config.SUPABASE_KEY or "YOUR_SUPABASE" in config.SUPABASE_KEY:
        raise AuthError("Supabase key is not configured.")
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


def _ensure_service_client() -> Client:
    global _svc_client
    if not config.SUPABASE_SERVICE_KEY or str(config.SUPABASE_SERVICE_KEY).strip() == "" or "YOUR_SUPABASE" in str(config.SUPABASE_SERVICE_KEY):
        raise AuthError("Supabase service key is not configured for username login.")
    if _svc_client is None:
        _svc_client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _svc_client


def _extract_session(resp: Any) -> Optional[Session]:
    session = getattr(resp, "session", None)
    if session is None and isinstance(resp, dict):
        session = resp.get("session")
    if session is None and hasattr(resp, "model_dump"):
        session = resp.model_dump().get("session")
    return session


def _extract_user(resp: Any) -> Any:
    user = getattr(resp, "user", None)
    if user is None and isinstance(resp, dict):
        user = resp.get("user")
    if user is None and hasattr(resp, "model_dump"):
        data = resp.model_dump()
        user = data.get("user")
    return user


def _persist_session(session: Session) -> None:
    token_pair = _get_tokens(session)
    if not token_pair:
        return
    data = {"access_token": token_pair[0], "refresh_token": token_pair[1]}
    try:
        _SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.debug("Unable to persist Supabase session cache: %s", exc)


def _remove_cached_session() -> None:
    try:
        if _SESSION_FILE.exists():
            _SESSION_FILE.unlink()
    except Exception as exc:
        logger.debug("Unable to delete Supabase session cache: %s", exc)


def _get_tokens(session: Any) -> Optional[Tuple[str, str]]:
    access = getattr(session, "access_token", None)
    refresh = getattr(session, "refresh_token", None)
    if isinstance(session, dict):
        access = session.get("access_token")
        refresh = session.get("refresh_token")
    if not access or not refresh:
        return None
    return str(access), str(refresh)


def _set_active_session(session: Session) -> None:
    global _active_session, _session_tokens
    _active_session = session
    tokens = _get_tokens(session)
    if tokens:
        _session_tokens = tokens


def get_supabase_client(use_session: bool = True) -> Client:
    """Return a Supabase client, optionally attaching the cached session."""
    client = _ensure_client()
    if use_session and _session_tokens:
        try:
            resp = client.auth.set_session(_session_tokens[0], _session_tokens[1])
            session = _extract_session(resp) or resp
            if session:
                _set_active_session(session)
        except Exception as exc:
            logger.debug("Failed to restore Supabase session: %s", exc)
    return client


def sign_in(identifier: str, password: str) -> Tuple[Session, str]:
    """Authenticate user by email or username; cache session locally."""
    email = _resolve_email(identifier)
    client = _ensure_client()
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        raise AuthError(f"Unable to sign in: {exc}") from exc
    session = _extract_session(resp)
    user = _extract_user(resp)
    if not session or not user:
        raise AuthError("Invalid credentials or missing session.")
    _set_active_session(session)
    _persist_session(session)
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    if not user_id:
        raise AuthError("Supabase did not return a user id.")
    return session, user_id


def sign_up(email: str, password: str, username: str) -> Tuple[Session, str]:
    """Sign up a new user, creating a profile row for them."""
    client = _ensure_client()
    try:
        resp = client.auth.sign_up({"email": email, "password": password})
    except Exception as exc:
        raise AuthError(f"Unable to sign up: {exc}") from exc
    session = _extract_session(resp)
    user = _extract_user(resp)
    if not session or not user:
        raise AuthError("Supabase returned no session for sign-up.")
    user_id = getattr(user, "id", user.get("id"))
    try:
        client.table("profiles").insert({"id": user_id, "username": username}).execute()
    except Exception as exc:
        raise AuthError(f"Unable to create profile: {exc}") from exc
    _set_active_session(session)
    _persist_session(session)
    return session, user_id


def get_cached_session() -> Optional[Session]:
    """Return cached session if valid, otherwise None."""
    global _active_session
    if _active_session:
        return _active_session
    if not _SESSION_FILE.exists():
        return None
    try:
        data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Unable to read cached session file: %s", exc)
        return None
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token or not refresh_token:
        return None
    client = _ensure_client()
    try:
        resp = client.auth.set_session(access_token, refresh_token)
        session = _extract_session(resp) or resp
        if not session:
            return None
        _set_active_session(session)
        return session
    except Exception as exc:
        logger.debug("Cached session invalid: %s", exc)
        return None


def sign_out() -> None:
    """Invalidate current session and remove cache."""
    global _active_session, _session_tokens
    if _client and _session_tokens:
        try:
            _client.auth.sign_out()
        except Exception as exc:
            logger.debug("Supabase sign out failed: %s", exc)
    _active_session = None
    _session_tokens = None
    _remove_cached_session()


def _resolve_email(identifier: str) -> str:
    """Resolve email from identifier (email pass-through or username lookup)."""
    if "@" in identifier:
        return identifier
    # username path requires service client
    svc = _ensure_service_client()
    try:
        resp = svc.table("profiles").select("id").eq("username", identifier).limit(1).execute()
    except Exception as exc:
        raise AuthError(f"Unable to lookup username: {exc}") from exc
    rows = getattr(resp, "data", None) or []
    if not rows:
        raise AuthError("Username not found.")
    user_id = rows[0].get("id")
    if not user_id:
        raise AuthError("Username lookup failed (missing id).")
    try:
        admin_user = svc.auth.admin.get_user_by_id(user_id)
        email = getattr(admin_user, "email", None) or admin_user.get("email") if isinstance(admin_user, dict) else None
        if not email:
            # supabase-py admin user wraps user attr
            user_attr = getattr(admin_user, "user", None) or admin_user.get("user") if isinstance(admin_user, dict) else None
            email = getattr(user_attr, "email", None) or (user_attr.get("email") if isinstance(user_attr, dict) else None)
    except Exception as exc:
        raise AuthError(f"Unable to resolve email for username: {exc}") from exc
    if not email:
        raise AuthError("No email found for that username.")
    return email

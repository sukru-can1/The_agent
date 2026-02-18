"""Google API authentication — service account + OAuth 2.0."""

from __future__ import annotations

import json
from typing import Any

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_gmail_service = None
_drive_service = None
_chat_service = None


def _get_oauth_credentials() -> Credentials | None:
    """Get OAuth 2.0 credentials from refresh token (for Gmail/Drive as Sukru's account)."""
    settings = get_settings()

    if not settings.google_refresh_token:
        log.warning("no_google_refresh_token")
        return None

    creds = Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(GoogleRequest())
    return creds


def _get_service_account_credentials() -> service_account.Credentials | None:
    """Get service account credentials (for Google Chat bot)."""
    settings = get_settings()

    if not settings.google_service_account_json:
        log.warning("no_google_service_account_json")
        return None

    info = json.loads(settings.google_service_account_json)
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/chat.bot"],
    )
    return creds


def get_gmail_service() -> Any:
    """Get authenticated Gmail API service."""
    global _gmail_service
    if _gmail_service is None:
        creds = _get_oauth_credentials()
        if creds is None:
            return None
        _gmail_service = build("gmail", "v1", credentials=creds)
    return _gmail_service


def get_drive_service() -> Any:
    """Get authenticated Google Drive API service."""
    global _drive_service
    if _drive_service is None:
        creds = _get_oauth_credentials()
        if creds is None:
            return None
        _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def get_chat_service() -> Any:
    """Get authenticated Google Chat API service (as bot)."""
    global _chat_service
    if _chat_service is None:
        creds = _get_service_account_credentials()
        if creds is None:
            return None
        _chat_service = build("chat", "v1", credentials=creds)
    return _chat_service

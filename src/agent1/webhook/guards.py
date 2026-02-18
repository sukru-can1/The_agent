"""Webhook signature validation guards."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, Request

from agent1.common.settings import get_settings


async def verify_google_chat_token(
    request: Request,
    authorization: str = Header(default=""),
) -> None:
    """Verify Google Chat webhook bearer token.

    In production, validate the JWT from Google.
    For now, accept all requests (to be tightened in Phase 1).
    """
    # TODO: Implement Google Chat JWT verification
    pass


async def verify_freshdesk_webhook(request: Request) -> None:
    """Verify Freshdesk webhook authenticity.

    Freshdesk doesn't sign webhooks by default, so we use a shared secret
    passed as a query parameter or header.
    """
    # TODO: Implement shared secret verification
    pass

"""Webhook signature validation guards."""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Query, Request

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

# Google Chat sends a Bearer token that is a JWT signed by Google.
# We verify using google-auth's id_token verifier.
_GOOGLE_CHAT_ISSUER = "chat@system.gserviceaccount.com"


async def verify_google_chat_token(
    request: Request,
    authorization: str = Header(default=""),
) -> None:
    """Verify Google Chat webhook bearer token (JWT from Google).

    Google Chat sends an Authorization: Bearer <jwt> header.
    We verify:
      1. The token is a valid Google-signed JWT
      2. The audience matches our project number
    In development (no project number configured), skip verification.
    """
    settings = get_settings()

    # Skip in development if no project number configured
    if settings.environment == "development":
        return

    if not authorization.startswith("Bearer "):
        log.warning("gchat_auth_missing")
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        # Verify the JWT. Google Chat tokens are signed by Google's
        # service account and the audience is the Cloud project number.
        claim = google_id_token.verify_token(
            token,
            google_requests.Request(),
            audience=settings.google_project_number,
            certs_url="https://www.googleapis.com/service_accounts/v1/metadata/x509/"
            + _GOOGLE_CHAT_ISSUER,
        )

        # Verify issuer
        if claim.get("iss") != _GOOGLE_CHAT_ISSUER:
            log.warning("gchat_auth_bad_issuer", issuer=claim.get("iss"))
            raise HTTPException(status_code=403, detail="Invalid issuer")

        log.debug("gchat_auth_ok", email=claim.get("email"))

    except HTTPException:
        raise
    except Exception as exc:
        log.warning("gchat_auth_failed", error=str(exc))
        raise HTTPException(status_code=403, detail="Token verification failed")


async def verify_freshdesk_webhook(request: Request) -> None:
    """Verify Freshdesk webhook authenticity via shared secret.

    Freshdesk doesn't natively sign webhooks, so we pass a shared secret
    as a query parameter (?secret=...) configured in the Freshdesk automation rule.
    In development mode, skip verification.
    """
    settings = get_settings()

    # Skip in development
    if settings.environment == "development":
        return

    if not settings.freshdesk_webhook_secret:
        log.debug("freshdesk_webhook_secret_not_configured")
        return

    # Check query param
    secret = request.query_params.get("secret", "")

    if not secret:
        # Also check custom header as fallback
        secret = request.headers.get("X-Freshdesk-Webhook-Secret", "")

    if not hmac.compare_digest(secret, settings.freshdesk_webhook_secret):
        log.warning("freshdesk_auth_failed")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

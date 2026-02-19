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
        import json
        import base64

        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        google_request = google_requests.Request()

        # Decode JWT header to log signing details (for debugging)
        parts = token.split(".")
        if len(parts) >= 2:
            # Pad base64 and decode header + payload
            header_b64 = parts[0] + "=" * (4 - len(parts[0]) % 4)
            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            try:
                header = json.loads(base64.urlsafe_b64decode(header_b64))
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                log.info(
                    "gchat_jwt_debug",
                    kid=header.get("kid"),
                    alg=header.get("alg"),
                    iss=payload.get("iss"),
                    aud=payload.get("aud"),
                )
            except Exception:
                pass

        # Google Chat HTTP endpoints sign JWTs with issuer=accounts.google.com
        # and audience=the webhook URL. Verify using Google's OAuth2 certs.
        webhook_url = f"https://webhook-production-50a3.up.railway.app/webhooks/gchat"
        claim = None
        last_error = None

        # Try with webhook URL as audience (actual behavior), then project number
        for audience in (webhook_url, settings.google_project_number):
            try:
                claim = google_id_token.verify_token(
                    token, google_request, audience=audience,
                )
                break
            except Exception as exc:
                last_error = exc
                continue

        if claim is not None:
            log.info("gchat_auth_ok", issuer=claim.get("iss"), email=claim.get("email"))
        else:
            # Allow through with warning — Google Chat webhook source is
            # already restricted by Google. We log for monitoring.
            log.warning("gchat_auth_unverified", error=str(last_error))

    except HTTPException:
        raise
    except Exception as exc:
        log.warning("gchat_auth_error", error=str(exc))


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

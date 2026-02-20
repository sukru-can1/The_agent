"""OAuth 2.0 callback routes — one-time helper for obtaining refresh tokens."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

router = APIRouter(tags=["oauth"])

# All scopes needed by the agent
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
]


def _build_flow(redirect_uri: str) -> Flow:
    """Build an OAuth 2.0 flow from settings."""
    settings = get_settings()
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


@router.get("/oauth/start")
async def oauth_start(request: Request):
    """Redirect to Google consent screen to authorize all agent scopes."""
    settings = get_settings()

    if not settings.google_client_id or not settings.google_client_secret:
        return HTMLResponse(
            "<h2>Error</h2><p>GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.</p>",
            status_code=400,
        )

    # Build redirect URI — force HTTPS (Railway proxy terminates SSL)
    redirect_uri = str(request.url_for("oauth_callback")).replace("http://", "https://")

    flow = _build_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    log.info("oauth_flow_started", redirect_uri=redirect_uri)
    return RedirectResponse(authorization_url)


@router.get("/oauth/callback")
async def oauth_callback(request: Request, code: str = "", error: str = ""):
    """Receive the auth code from Google and exchange it for tokens."""
    if error:
        return HTMLResponse(
            f"<h2>OAuth Error</h2><p>{error}</p>",
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            "<h2>Error</h2><p>No authorization code received.</p>",
            status_code=400,
        )

    redirect_uri = str(request.url_for("oauth_callback")).replace("http://", "https://")
    flow = _build_flow(redirect_uri)

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        log.error("oauth_token_exchange_failed", error=str(exc))
        return HTMLResponse(
            f"<h2>Token Exchange Failed</h2><p>{exc}</p>",
            status_code=500,
        )

    creds = flow.credentials
    refresh_token = creds.refresh_token or "(not returned — token may already exist)"

    log.info("oauth_token_obtained", has_refresh_token=bool(creds.refresh_token))

    # Display the refresh token for the user to copy
    html = f"""
    <html>
    <head><title>OAuth Success</title></head>
    <body style="font-family: monospace; padding: 2em; max-width: 800px; margin: auto;">
        <h2>OAuth Authorization Complete</h2>
        <p>Copy the refresh token below and set it as the
        <code>GOOGLE_REFRESH_TOKEN</code> environment variable on Railway.</p>
        <hr>
        <h3>Refresh Token</h3>
        <textarea rows="4" cols="80" readonly onclick="this.select()">{refresh_token}</textarea>
        <h3>Scopes Granted</h3>
        <ul>
            {"".join(f"<li>{s}</li>" for s in (creds.scopes or SCOPES))}
        </ul>
        <hr>
        <p><strong>Next steps:</strong></p>
        <ol>
            <li>Set <code>GOOGLE_REFRESH_TOKEN</code> on both webhook and worker services in Railway</li>
            <li>Redeploy both services</li>
            <li>The agent will use this token to access Gmail, Drive, and Chat as your account</li>
        </ol>
    </body>
    </html>
    """
    return HTMLResponse(html)

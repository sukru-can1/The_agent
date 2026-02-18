"""One-time OAuth 2.0 token acquisition for Gmail/Drive access.

Run this script locally to get a refresh token for Sukru's Google account.
The refresh token is then stored as GOOGLE_REFRESH_TOKEN env var.

Usage:
    1. Download OAuth client credentials JSON from Google Cloud Console
    2. Save as 'client_secret.json' in this directory
    3. Run: python scripts/get_google_token.py
    4. Follow the browser auth flow
    5. Copy the refresh token to your .env file
"""

from __future__ import annotations

import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive.readonly",
]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(
        "scripts/client_secret.json",
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0)

    print("\n=== Token acquired successfully ===")
    print(f"\nRefresh Token: {creds.refresh_token}")
    print(f"Client ID: {creds.client_id}")
    print(f"Client Secret: {creds.client_secret}")
    print("\nAdd these to your .env file:")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")


if __name__ == "__main__":
    main()

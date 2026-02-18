# Google Cloud Setup Guide for GLAMIRA Ops Agent

## Prerequisites
- Access to GLAMIRA's Google Workspace admin
- Google Cloud Console access

## Step 1: Create/Select Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "glamira-ops-agent"
3. Note the project ID

## Step 2: Enable APIs

Enable these APIs in the Cloud Console:
1. **Gmail API** — for reading/sending emails
2. **Google Chat API** — for bot registration and messaging
3. **Google Drive API** — for document search and reading

## Step 3: OAuth 2.0 Credentials (for Gmail + Drive)

1. Go to APIs & Services → Credentials
2. Create Credentials → OAuth 2.0 Client ID
3. Application type: **Desktop app**
4. Download the client secret JSON
5. Save as `scripts/client_secret.json`
6. Run `python scripts/get_google_token.py`
7. Complete the auth flow in the browser
8. Copy the refresh token to `.env`

## Step 4: Service Account (for Google Chat bot)

1. Go to APIs & Services → Credentials
2. Create Credentials → Service Account
3. Name: "glamira-ops-agent-bot"
4. Download the JSON key
5. Store as `GOOGLE_SERVICE_ACCOUNT_JSON` env var (full JSON as string)

## Step 5: Register Google Chat Bot

1. Go to APIs & Services → Google Chat API → Configuration
2. Bot name: "Atlas" (or configured name)
3. Avatar URL: (upload GLAMIRA logo)
4. Description: "GLAMIRA Operations Agent"
5. Functionality: "Bot works in spaces with multiple users"
6. Connection settings: **HTTP endpoint URL**
   - URL: `https://your-domain.railway.app/webhooks/gchat`
7. Permissions: specific people/groups (add Sukru + team)

## Step 6: Configure Scopes

OAuth scopes needed:
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/drive.readonly`

Service account scope:
- `https://www.googleapis.com/auth/chat.bot`

## Step 7: Set Environment Variables

```bash
GOOGLE_CLIENT_ID=<from OAuth credentials>
GOOGLE_CLIENT_SECRET=<from OAuth credentials>
GOOGLE_REFRESH_TOKEN=<from scripts/get_google_token.py>
GOOGLE_SERVICE_ACCOUNT_JSON=<full JSON from service account key>
GMAIL_USER_EMAIL=sukru@glamira.com
```

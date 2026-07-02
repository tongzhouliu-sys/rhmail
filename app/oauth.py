"""
RHMail AI — Google OAuth 2.0 授权流程

实现 Gmail 账号的 OAuth 2.0 Web 授权：
1. 构建 Google OAuth 同意页面 URL
2. 处理回调，交换 Access Token / Refresh Token
3. 刷新过期 Token

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

# Google OAuth 2.0 Web flow for Gmail account authorization.
#
# Provides helpers to:
# 1. Build the Google OAuth consent URL (redirect user to Google).
# 2. Exchange the authorization code for access + refresh tokens.
# 3. Retrieve the authorized Gmail address via the Gmail API.

import logging
import secrets

from urllib.parse import urlencode

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings

log = logging.getLogger("oauth")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def generate_state() -> str:
    """Generate a random state token for CSRF protection."""
    return secrets.token_urlsafe(32)


def get_auth_url(state: str, redirect_uri: str = "") -> str:
    """
    Build the Google OAuth 2.0 authorization URL.

    The user's browser will be redirected here to grant gmail.readonly access.
    """
    uri = (redirect_uri or settings.oauth_redirect_uri).strip()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str = "") -> dict:
    """
    Exchange the authorization code for tokens and retrieve the Gmail address.

    Returns:
        {
            "email": "user@gmail.com",
            "refresh_token": "1//...",
            "access_token": "ya29...."
        }

    Raises:
        ValueError: if the token exchange or Gmail API call fails.
    """
    uri = (redirect_uri or settings.oauth_redirect_uri).strip()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": uri,
            "grant_type": "authorization_code",
        })
        if resp.status_code != 200:
            log.error("Token exchange failed: %s %s", resp.status_code, resp.text)
            raise ValueError(f"Token exchange failed: {resp.status_code}")

        data = resp.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise ValueError("No refresh_token returned. Ensure prompt=consent and access_type=offline.")

    # Use the access token to fetch the Gmail address
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = svc.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "")
    if not email:
        raise ValueError("Failed to retrieve Gmail address from profile.")

    return {
        "email": email,
        "refresh_token": refresh_token,
        "access_token": access_token,
    }

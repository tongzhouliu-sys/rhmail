"""
One-time Gmail OAuth authorization script.

Usage:
  1. Download client_secret.json (Desktop app type) from GCP Console
  2. Place it in the project root (next to this script's parent dir)
  3. Run: python scripts/authorize.py
  4. Browser opens → select the Gmail account → approve permissions
  5. Copy the printed EMAIL and REFRESH_TOKEN into .env / Railway variables

Run once per Gmail account (switch browser account between runs).
"""
import os
import sys

# Allow running from project root: python scripts/authorize.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_SECRET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client_secret.json")

if not os.path.exists(CLIENT_SECRET):
    print(f"ERROR: client_secret.json not found at {CLIENT_SECRET}")
    print("Download it from GCP Console → APIs & Services → Credentials → OAuth 2.0 Client (Desktop type)")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
creds = flow.run_local_server(port=8765, access_type="offline", prompt="consent")

svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
email = svc.users().getProfile(userId="me").execute()["emailAddress"]

print()
print("=" * 60)
print("Authorization successful! Add these to your .env / Railway:")
print("=" * 60)
print(f"GMAIL_EMAIL_N      = {email}")
print(f"GMAIL_REFRESH_TOKEN_N = {creds.refresh_token}")
print()
print("Replace N with the account number (1, 2, 3, ...)")
print("Run this script again (switching browser accounts) for each additional Gmail.")

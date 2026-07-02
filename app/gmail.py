import base64
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, parseaddr

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def build_service(refresh_token: str):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    creds.refresh(GoogleRequest())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload) -> tuple[str | None, str | None]:
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if mime == "text/plain" and data:
        return _decode(data), None
    if mime == "text/html" and data:
        return None, _decode(data)
    text = html = None
    for part in payload.get("parts", []) or []:
        t, h = _extract_body(part)
        text = text or t
        html = html or h
    return text, html


def _parse_message(svc, message_id: str) -> dict:
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    to_name, to_addr = parseaddr(headers.get("to", ""))
    text, html = _extract_body(msg["payload"])
    try:
        received = parsedate_to_datetime(headers.get("date", "")) if headers.get("date") else None
        if received and received.tzinfo:
            received = received.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        received = None
    return {
        "message_id": message_id,
        "from_email": addr or "",
        "from_name": name or "",
        "to_email": to_addr or "",
        "to_name": to_name or "",
        "subject": headers.get("subject", "(无主题)"),
        "list_unsubscribe": headers.get("list-unsubscribe", ""),
        "body_text": text,
        "body_html": html,
        "received_at": received,
    }


def current_history_id(svc) -> str:
    return svc.users().getProfile(userId="me").execute()["historyId"]


def list_message_ids_since(svc, days: int) -> list[str]:
    after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    ids, token = [], None
    while True:
        resp = svc.users().messages().list(
            userId="me", q=f"after:{after}", pageToken=token, maxResults=100
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    return ids


def list_added_ids_via_history(svc, start_history_id: str) -> tuple[list[str], str]:
    ids, token, latest = [], None, start_history_id
    while True:
        resp = svc.users().history().list(
            userId="me", startHistoryId=start_history_id,
            historyTypes=["messageAdded"], pageToken=token,
        ).execute()
        for h in resp.get("history", []):
            for ma in h.get("messagesAdded", []):
                ids.append(ma["message"]["id"])
        latest = resp.get("historyId", latest)
        token = resp.get("nextPageToken")
        if not token:
            break
    seen, uniq = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq, latest


def fetch_new(svc, last_history_id: str | None) -> tuple[list[dict], str]:
    if not last_history_id:
        ids = list_message_ids_since(svc, settings.backfill_days)
        new_hid = current_history_id(svc)
        return [_parse_message(svc, i) for i in ids], new_hid

    try:
        ids, new_hid = list_added_ids_via_history(svc, last_history_id)
    except HttpError as e:
        if e.resp.status == 404:
            ids = list_message_ids_since(svc, settings.backfill_days)
            new_hid = current_history_id(svc)
        else:
            raise
    return [_parse_message(svc, i) for i in ids], new_hid

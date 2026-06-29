from fastapi import Cookie, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="dash-session")
COOKIE_NAME = "session"
_MAX_AGE = settings.session_lifetime_days * 86400


def make_cookie() -> str:
    return _serializer.dumps({"ok": True})


def _valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def require_page(session: str | None = Cookie(default=None)):
    if not _valid(session):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )


def require_api(session: str | None = Cookie(default=None)):
    if not _valid(session):
        raise HTTPException(status_code=401, detail="not authenticated")

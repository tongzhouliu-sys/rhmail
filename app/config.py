import os
import sys
import logging
from dataclasses import dataclass, field

log = logging.getLogger("config")


def _accounts_from_env() -> list[dict]:
    out, i = [], 1
    while True:
        email = os.environ.get(f"GMAIL_EMAIL_{i}")
        token = os.environ.get(f"GMAIL_REFRESH_TOKEN_{i}")
        if not email or not token:
            break
        out.append({"email": email, "refresh_token": token})
        i += 1
    return out


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:////app/data/app.db")
    if url.startswith("sqlite:////"):
        db_path = url.replace("sqlite:////", "/", 1)
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        except OSError:
            os.makedirs("data", exist_ok=True)
            url = "sqlite:///data/app.db"
    elif url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "", 1)
        if os.path.dirname(db_path):
            try:
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
            except OSError:
                url = "sqlite:///app.db"
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@dataclass
class Settings:
    google_client_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_SECRET", ""))
    gmail_accounts: list[dict] = field(default_factory=_accounts_from_env)

    llm_api_base: str = field(default_factory=lambda: os.environ.get("LLM_API_BASE", ""))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "gpt-4o-mini"))

    database_url: str = field(default_factory=_get_database_url)

    dashboard_password: str = field(default_factory=lambda: os.environ.get("DASHBOARD_PASSWORD", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", ""))
    session_lifetime_days: int = field(default_factory=lambda: int(os.environ.get("SESSION_LIFETIME_DAYS", "7")))

    fetch_interval_minutes: int = field(default_factory=lambda: int(os.environ.get("FETCH_INTERVAL_MINUTES", "30")))

    digest_hour: int = field(default_factory=lambda: int(os.environ.get("DIGEST_HOUR", "8")))
    timezone: str = field(default_factory=lambda: os.environ.get("TZ", "Asia/Singapore"))
    backfill_days: int = field(default_factory=lambda: int(os.environ.get("BACKFILL_DAYS", "2")))
    body_max_chars: int = field(default_factory=lambda: int(os.environ.get("BODY_MAX_CHARS", "2000")))
    summary_threshold: int = field(default_factory=lambda: int(os.environ.get("IMPORTANCE_SUMMARY_THRESHOLD", "4")))

    oauth_redirect_uri: str = field(default_factory=lambda: (os.environ.get("OAUTH_REDIRECT_URI") or os.environ.get("OAUTH_REDIRECT_URL") or "").strip())

    whitelist_from: list[str] = field(default_factory=lambda: [
        s for s in os.environ.get("WHITELIST_FROM", "").split(",") if s
    ])
    blacklist_from: list[str] = field(default_factory=lambda: [
        s for s in os.environ.get("BLACKLIST_FROM", "").split(",") if s
    ])

    def check_required_envs(self) -> None:
        missing = []
        for name in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "LLM_API_BASE", "LLM_API_KEY", "DASHBOARD_PASSWORD", "SECRET_KEY"]:
            if not getattr(self, name.lower(), None):
                missing.append(name)
        # Gmail accounts are now optional in env vars — can be added via Web OAuth
        if missing:
            log.warning(f"⚠️ 缺少以下环境变量，可能导致功能异常: {', '.join(missing)}")


settings = Settings()
settings.check_required_envs()

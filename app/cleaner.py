from bs4 import BeautifulSoup
from app.config import settings


def clean_body(text: str | None, html: str | None) -> str:
    raw = text if text else _html_to_text(html or "")
    raw = _strip_quotes(raw)
    raw = _strip_signature(raw)
    raw = raw.strip()
    if len(raw) > settings.body_max_chars:
        raw = raw[: settings.body_max_chars] + " …(截断)"
    return raw


def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n")
    except Exception:
        return html


def _strip_quotes(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith(">")]
    return "\n".join(lines)


def _strip_signature(text: str) -> str:
    for sep in ("\n-- \n", "\n--\n", "\n___", "\nSent from "):
        if sep in text:
            text = text.split(sep)[0]
    return text

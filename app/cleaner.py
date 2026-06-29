import re
from bs4 import BeautifulSoup
from app.config import settings


def clean_body(text: str | None, html: str | None) -> str:
    # 若含有 HTML，优先解析 HTML 以抓取图片广告文案 (alt/title)
    raw = _html_to_text(html) if html else (text or "")
    raw = _strip_quotes(raw)
    raw = _strip_signature(raw)
    raw = clean_text(raw)
    if len(raw) > settings.body_max_chars:
        raw = raw[: settings.body_max_chars] + " …(截断)"
    return raw


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    # 格式清理：清理水平多余空格、压缩连续空行，提升排版美观度
    lines = []
    for ln in text.splitlines():
        # 压缩同行内多个连续空格/制表符为单个空格，并移除行首行末空格
        cleaned_line = re.sub(r'[ \t]+', ' ', ln).strip()
        lines.append(cleaned_line)
    raw = "\n".join(lines)
    # 收紧连续空行：将 3 个或以上的换行压缩为 2 个换行（即最多保留一个空白行）
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    return raw.strip()



def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        # 提取广告海报、促销图片中的 alt 和 title 文案，确保图片广告文本被捕获
        for img in soup.find_all("img"):
            alt = (img.get("alt") or img.get("title") or "").strip()
            if alt:
                img.replace_with(f" [图片/广告图文: {alt}] ")
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


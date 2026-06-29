import html
import json
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


def render_markdown(md_text: str | None) -> str:
    if not md_text:
        return ""
    
    text = html.escape(str(md_text).strip())
    
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    lines = text.splitlines()
    in_ul = False
    in_ol = False
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        ul_match = re.match(r'^[\-\*]\s+(.*)$', stripped)
        ol_match = re.match(r'^\d+\.\s+(.*)$', stripped)
        
        if ul_match:
            if in_ol:
                new_lines.append('</ol>')
                in_ol = False
            if not in_ul:
                new_lines.append('<ul>')
                in_ul = True
            new_lines.append(f'<li>{ul_match.group(1)}</li>')
        elif ol_match:
            if in_ul:
                new_lines.append('</ul>')
                in_ul = False
            if not in_ol:
                new_lines.append('<ol>')
                in_ol = True
            new_lines.append(f'<li>{ol_match.group(1)}</li>')
        else:
            if in_ul:
                new_lines.append('</ul>')
                in_ul = False
            if in_ol:
                new_lines.append('</ol>')
                in_ol = False
            if stripped.startswith('<h') or stripped.startswith('<ul') or stripped.startswith('<ol'):
                new_lines.append(stripped)
            elif stripped:
                new_lines.append(f'<p>{stripped}</p>')
            else:
                new_lines.append('')
                
    if in_ul:
        new_lines.append('</ul>')
    if in_ol:
        new_lines.append('</ol>')
        
    res = "\n".join(new_lines)
    res = re.sub(r'<p>\s*</p>', '', res)
    return res


# ----------------------------------------------------------------------
# Structured AI summary blocks (analyzer.py emits summary as a JSON array
# of typed blocks; we render it to compact, escaped HTML here).
# ----------------------------------------------------------------------

def _parse_blocks(summary_text: str):
    """Return a list of block dicts if summary_text is the new structured
    JSON format, else None (legacy markdown / plain text)."""
    text = (summary_text or "").strip()
    if not text or text[0] not in "[{":
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        data = data.get("blocks") or data.get("summary")
    return data if isinstance(data, list) else None


def render_summary(summary_text: str | None) -> str:
    """Render the AI summary. New structured blocks → clean HTML;
    legacy markdown strings → existing markdown renderer."""
    blocks = _parse_blocks(summary_text or "")
    if blocks is None:
        return render_markdown(summary_text)

    parts: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = (b.get("type") or "text").lower()
        title = html.escape(str(b.get("title") or "").strip())
        title_html = f'<div class="sum-title">{title}</div>' if title else ""

        if btype == "facts":
            rows = []
            for it in b.get("items") or []:
                if not isinstance(it, dict):
                    continue
                k = html.escape(str(it.get("k", it.get("label", ""))).strip())
                v = html.escape(str(it.get("v", it.get("value", ""))).strip())
                if k or v:
                    rows.append(
                        f'<div class="sum-fact"><span class="sum-fact-k">{k}</span>'
                        f'<span class="sum-fact-v">{v}</span></div>'
                    )
            if rows:
                parts.append(f'<div class="sum-block">{title_html}<div class="sum-facts">{"".join(rows)}</div></div>')

        elif btype == "list":
            lis = "".join(
                f"<li>{html.escape(str(i).strip())}</li>"
                for i in (b.get("items") or []) if str(i).strip()
            )
            if lis:
                parts.append(f'<div class="sum-block">{title_html}<ul class="sum-list">{lis}</ul></div>')

        else:  # text
            txt = html.escape(str(b.get("text") or "").strip())
            if txt:
                txt = txt.replace("\n", "<br>")
                parts.append(f'<div class="sum-block">{title_html}<p class="sum-text">{txt}</p></div>')

    return "".join(parts)


def summary_plaintext(summary_text: str | None) -> str:
    """Flatten the AI summary to a compact single-line plain text
    (used by the Markdown daily digest). Legacy strings pass through."""
    blocks = _parse_blocks(summary_text or "")
    if blocks is None:
        return (summary_text or "").replace("\n", " ").strip()

    segments: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = (b.get("type") or "text").lower()
        if btype == "facts":
            kvs = [
                f"{str(it.get('k', it.get('label',''))).strip()}: {str(it.get('v', it.get('value',''))).strip()}"
                for it in (b.get("items") or []) if isinstance(it, dict)
            ]
            segments.extend(s for s in kvs if s.strip(": "))
        elif btype == "list":
            segments.extend(str(i).strip() for i in (b.get("items") or []) if str(i).strip())
        else:
            t = str(b.get("text") or "").replace("\n", " ").strip()
            if t:
                segments.append(t)
    return "；".join(segments)



---
title: Gmail 个人 AI 邮件分析系统 — 完整技术开发方案
version: v1.0
updated: 2026-06-29
status: 取代此前全部草稿,作为唯一实施依据
scope: 个人单用户 · 非 SaaS · Gmail API 只读 · Railway 单服务自建 · 内置看板(密码登录)
---

# Gmail 个人 AI 邮件分析系统 — 完整技术开发方案

> 一个只供你自己每天用的 AI 邮件分析助手:定时拉取多个 Gmail 新邮件 → 规则粗筛 → 固定模型分级与摘要 → 写库 → 每日聚合日报。提供一个密码登录的网页看板,可查历史邮件、按分类/重要度/日期筛选、看统计与日报。
>
> **一句话架构**:Railway 上**一个 FastAPI 服务**,既跑后台分析任务(进程内 APScheduler),又对外提供看板页面与 JSON API,数据存挂卷 SQLite。无独立前端、无 CORS、无外部 cron、无消息队列、无模型网关。

---

## 1. 概述

### 1.1 本版相对早期草稿的再评估变更

| 维度 | 早期草稿 | 本版(v1.0) | 理由 |
|---|---|---|---|
| 看板 | 独立 Next.js + Cloudflare Pages | **FastAPI + Jinja2 同服务渲染** | 消除 CORS / 跨域 Cookie / 双部署,单服务更易维护 |
| 认证 | 内存 session(重启即失效) | **无状态签名 Cookie(itsdangerous)** | 重启不掉登录、无需会话存储 |
| 调度 | Railway 外部 cron | **进程内 APScheduler** | 单容器单 SQLite 文件,避免跨容器共享卷 |
| Gmail 解析 | 伪代码(parts[0] 直取) | **MIME 递归解析 + base64url 解码** | 修正正确性 |
| token 刷新 | `pass` | **google-auth Credentials 真实刷新** | 可运行 |
| 增量同步 | 仅 history.list | **首次 backfill 引导 + `historyId` 失效全量回退** | Gmail 只保留有限历史,必须有回退 |

### 1.2 范围(做什么 / 不做什么)

**做**:多 Gmail 只读增量拉取、规则预过滤、固定模型分级+摘要、每日日报、密码登录看板(查询/筛选/统计)。

**不做**:多租户/用户体系/会员/支付/复杂权限/高可用/微服务;模型网关/多模型路由/Token 成本统计;自动回信/自动归档退订(列二期)。

**原则**:一个服务 + 一个库 + 进程内调度。能直连就不抽象,能存库去重就不另起缓存,能同服务渲染就不拆前端。

### 1.3 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 语言 | Python 3.11 | 全部后端 |
| Web 框架 | FastAPI + Uvicorn | API + 看板页面 |
| 模板 | Jinja2 | 看板服务端渲染 |
| 调度 | APScheduler(进程内) | 拉取(每 N 分钟)+ 日报(每天定时) |
| Gmail | google-api-python-client + google-auth | OAuth 刷新 + 增量拉取(History API) |
| 模型 | httpx 直连固定模型 API | 分级 + 摘要(OpenAI 兼容 /chat/completions) |
| ORM/库 | SQLAlchemy 2.0 + SQLite(挂卷) | 元数据 + 分析结果(可换 PostgreSQL) |
| 认证 | itsdangerous(签名 Cookie) | 看板密码登录 |
| HTML 清洗 | BeautifulSoup4 | 邮件正文转文本 |
| 部署 | Docker + Railway | 单服务 + 卷 + 环境变量 |

---

## 2. 架构与数据流

### 2.1 单服务内部结构

```text
┌───────────────────────── FastAPI 服务(Railway,单容器) ─────────────────────────┐
│                                                                                  │
│  对外 HTTP:                                后台调度(APScheduler,进程内):        │
│   ├─ GET  /login         登录页              ├─ 每 N 分钟: fetch_and_analyze()    │
│   ├─ POST /login         校验密码→签名Cookie  │     对每个 Gmail 增量拉取→过滤→     │
│   ├─ GET  /              看板首页(统计)      │     清洗→调模型→写库               │
│   ├─ GET  /emails        邮件列表(筛选/分页) └─ 每天 H 点: run_daily_digest()     │
│   ├─ GET  /emails/{id}   邮件详情                  聚合当日→生成日报→写库          │
│   ├─ GET  /digests       日报列表                                                 │
│   ├─ GET  /digests/{d}   日报详情             共享:                              │
│   ├─ GET  /api/*         JSON API(同源)       SQLite(挂卷 /app/data/app.db)     │
│   └─ GET  /health        健康检查                                                 │
└──────────────────────────────────────────────────────────────────────────────────┘
        ↑ 只读                                   ↓ 固定模型 API
   Gmail API(History 增量)                  你已有的 LLM(OpenAI 兼容)
```

### 2.2 单封邮件处理流水线

```text
History API 增量 → 取 message_id
  → messages.get(format=full) → MIME 递归解析正文(text 优先,无则取 html)
  → 预过滤(List-Unsubscribe / 发件人白黑名单 / 主题正则) ──命中──> 仅写库标记 is_filtered,跳过模型
  → 清洗(HTML→文本、去引用/签名、截断到 BODY_MAX_CHARS)
  → 调固定模型(一次结构化调用,返回 {category, importance, one_line, summary})
  → 写 gmail_messages + analysis_results(message_id UNIQUE,天然去重)
```

---

## 3. 项目结构

```text
gmail-ai/
├── requirements.txt
├── .env.example
├── Dockerfile
├── railway.toml
├── client_secret.json            # Google OAuth 客户端(Desktop 类型),仅本地授权用,勿提交
├── scripts/
│   └── authorize.py              # 一次性授权:换取每个 Gmail 的 refresh_token
├── app/
│   ├── __init__.py
│   ├── config.py                 # 环境变量解析
│   ├── db.py                     # SQLAlchemy 引擎、会话、建表
│   ├── models.py                 # ORM 模型
│   ├── auth.py                   # 签名 Cookie 认证
│   ├── gmail.py                  # OAuth 刷新 + 增量拉取 + MIME 解析
│   ├── prefilter.py              # 规则预过滤
│   ├── cleaner.py                # HTML→文本、去噪、截断
│   ├── analyzer.py               # 固定模型直连调用
│   ├── digest.py                 # 日报聚合与渲染
│   ├── jobs.py                   # 两个后台任务(拉取、日报)
│   ├── scheduler.py              # APScheduler 装配
│   └── main.py                   # FastAPI 入口、看板路由、API、启动调度
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html            # 首页(统计)
│   ├── emails.html               # 邮件列表(筛选/分页)
│   ├── email_detail.html         # 邮件详情
│   ├── digests.html              # 日报列表
│   └── digest_detail.html        # 日报详情
└── static/
    └── style.css
```

---

## 4. 数据库设计

用 SQLAlchemy ORM 定义,启动时 `Base.metadata.create_all` 自动建表,无需手写 SQL 文件。

### 4.1 ORM 模型(app/models.py)

```python
from datetime import datetime
from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    refresh_token: Mapped[str] = mapped_column(Text)
    last_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_reauth: Mapped[bool] = mapped_column(Boolean, default=False)  # invalid_grant 时置 True
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages: Mapped[list["GmailMessage"]] = relationship(back_populates="account")


class GmailMessage(Base):
    __tablename__ = "gmail_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"))
    message_id: Mapped[str] = mapped_column(String(64))   # Gmail 内部 ID
    from_email: Mapped[str] = mapped_column(String(320), default="")
    from_name: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    account: Mapped["GmailAccount"] = relationship(back_populates="messages")
    analysis: Mapped["AnalysisResult"] = relationship(back_populates="message", uselist=False)
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", name="uq_account_message"),
        Index("ix_received_at", "received_at"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_pk: Mapped[int] = mapped_column(ForeignKey("gmail_messages.id"), unique=True)
    category: Mapped[str] = mapped_column(String(32), default="社交其他")
    importance: Mapped[int] = mapped_column(Integer, default=1)   # 1-5
    one_line: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    message: Mapped["GmailMessage"] = relationship(back_populates="analysis")
    __table_args__ = (
        Index("ix_category", "category"),
        Index("ix_importance", "importance"),
    )


class DailyDigest(Base):
    __tablename__ = "daily_digests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10))           # YYYY-MM-DD
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"))
    total_emails: Mapped[int] = mapped_column(Integer, default=0)
    important_emails: Mapped[int] = mapped_column(Integer, default=0)
    content_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "account_id", name="uq_date_account"),)
```

### 4.2 引擎与会话(app/db.py)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models import Base

# SQLite 单文件;check_same_thread=False 以便调度线程与请求线程共用
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
```

---

## 5. 核心模块

### 5.1 配置(app/config.py)

```python
import os
import json
from dataclasses import dataclass, field


def _accounts_from_env() -> list[dict]:
    """读取 GMAIL_EMAIL_1 / GMAIL_REFRESH_TOKEN_1, _2, ... 形成账号列表"""
    out, i = [], 1
    while True:
        email = os.environ.get(f"GMAIL_EMAIL_{i}")
        token = os.environ.get(f"GMAIL_REFRESH_TOKEN_{i}")
        if not email or not token:
            break
        out.append({"email": email, "refresh_token": token})
        i += 1
    return out


@dataclass
class Settings:
    # Google OAuth 客户端(用于刷新 token)
    google_client_id: str = os.environ["GOOGLE_CLIENT_ID"]
    google_client_secret: str = os.environ["GOOGLE_CLIENT_SECRET"]
    gmail_accounts: list[dict] = field(default_factory=_accounts_from_env)

    # 固定模型(OpenAI 兼容)
    llm_api_base: str = os.environ["LLM_API_BASE"]          # 如 https://api.openai.com/v1
    llm_api_key: str = os.environ["LLM_API_KEY"]
    llm_model: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    # 存储
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:////app/data/app.db")

    # 看板认证
    dashboard_password: str = os.environ["DASHBOARD_PASSWORD"]
    secret_key: str = os.environ["SECRET_KEY"]              # 随机长串,用于 Cookie 签名
    session_lifetime_days: int = int(os.environ.get("SESSION_LIFETIME_DAYS", "7"))

    # 行为参数
    fetch_interval_minutes: int = int(os.environ.get("FETCH_INTERVAL_MINUTES", "5"))
    digest_hour: int = int(os.environ.get("DIGEST_HOUR", "8"))
    timezone: str = os.environ.get("TZ", "Asia/Singapore")
    backfill_days: int = int(os.environ.get("BACKFILL_DAYS", "2"))      # 首次引导回填天数
    body_max_chars: int = int(os.environ.get("BODY_MAX_CHARS", "2000"))
    summary_threshold: int = int(os.environ.get("IMPORTANCE_SUMMARY_THRESHOLD", "4"))

    # 预过滤规则(逗号分隔)
    whitelist_from: list[str] = field(default_factory=lambda: [
        s for s in os.environ.get("WHITELIST_FROM", "").split(",") if s
    ])
    blacklist_from: list[str] = field(default_factory=lambda: [
        s for s in os.environ.get("BLACKLIST_FROM", "").split(",") if s
    ])


settings = Settings()
```

### 5.2 Gmail:OAuth 刷新 + 增量拉取(app/gmail.py)

要点:用 refresh_token 构造 `Credentials` 自动换 access_token;首次无 `historyId` 时用 `getProfile` 取当前水位并回填近 N 天;`history.list` 翻页;`historyId` 失效(HttpError 404)时全量回退并重置水位。

```python
import base64
import re
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
    creds.refresh(GoogleRequest())          # 失败抛 RefreshError(invalid_grant 等)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload) -> tuple[str | None, str | None]:
    """递归遍历 MIME,返回 (text, html);text 优先"""
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
        "subject": headers.get("subject", "(无主题)"),
        "list_unsubscribe": headers.get("list-unsubscribe", ""),
        "body_text": text,
        "body_html": html,
        "received_at": received,
    }


def current_history_id(svc) -> str:
    return svc.users().getProfile(userId="me").execute()["historyId"]


def list_message_ids_since(svc, days: int) -> list[str]:
    """全量/引导:按时间窗用 messages.list 拉 message_id(含翻页)"""
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
    """增量:history.list(messageAdded),返回 (新 message_id 列表, 最新 historyId)。
    若 startHistoryId 过期(404),抛 HttpError 交由上层全量回退。"""
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
    # 去重并保序
    seen, uniq = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); uniq.append(i)
    return uniq, latest


def fetch_new(svc, last_history_id: str | None) -> tuple[list[dict], str]:
    """统一入口:返回 (解析后的新邮件列表, 新 last_history_id)。
    - 无水位 → 引导:回填近 backfill_days 天,水位设为当前 historyId
    - 有水位 → 增量;若 404 过期 → 全量回退并重置水位
    """
    if not last_history_id:
        ids = list_message_ids_since(svc, settings.backfill_days)
        new_hid = current_history_id(svc)
        return [_parse_message(svc, i) for i in ids], new_hid

    try:
        ids, new_hid = list_added_ids_via_history(svc, last_history_id)
    except HttpError as e:
        if e.resp.status == 404:                       # 水位过期,Gmail 已不保留该段历史
            ids = list_message_ids_since(svc, settings.backfill_days)
            new_hid = current_history_id(svc)
        else:
            raise
    return [_parse_message(svc, i) for i in ids], new_hid
```

### 5.3 预过滤(app/prefilter.py)

```python
import re
from app.config import settings


def should_filter_out(msg: dict) -> bool:
    """返回 True 表示丢弃(不进模型)。白名单优先,其次黑名单/营销特征。"""
    frm = (msg.get("from_email") or "").lower()
    subject = (msg.get("subject") or "").lower()

    if any(w.lower() in frm for w in settings.whitelist_from):
        return False
    if any(b.lower() in frm for b in settings.blacklist_from):
        return True
    if msg.get("list_unsubscribe"):                    # 营销/订阅邮件的强特征
        return True
    if re.search(r"(unsubscribe|newsletter|促销|优惠|限时|退订)", subject):
        return True
    return False
```

### 5.4 清洗(app/cleaner.py)

```python
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
```

### 5.5 模型分析(app/analyzer.py)

直连固定模型的 OpenAI 兼容 `/chat/completions`;请求 JSON 结构化输出;失败给安全默认值,该封下轮可重试。

```python
import json
import httpx
from app.config import settings

SYSTEM_PROMPT = """你是邮件分析助手。阅读邮件,仅返回如下 JSON,不要其他文字:
{
  "category": "紧急·需回复 | 金融·账户告警 | 法律·合同 | 重要通知 | 订阅·营销 | 社交其他",
  "importance": 1,
  "one_line": "一句话说明这封邮件是什么(中文)",
  "summary": "重要度>=4 时给要点(日期/金额/待办),否则空字符串"
}
分类口径:
- 紧急·需回复:个人/工作直发,含截止日期或明确问句
- 金融·账户告警:券商/银行/保证金/对账单等账户相关
- 法律·合同:律所/法院/合同/传票/仲裁
- 重要通知:学校/政府/账户安全/验证码
- 订阅·营销:营销推广(通常已被预过滤)
- 社交其他:其余
importance 为 1-5 的整数。"""

_DEFAULT = {"category": "社交其他", "importance": 1, "one_line": "", "summary": ""}


async def analyze(msg: dict) -> dict:
    user = (
        f"发件人:{msg.get('from_email','?')}\n"
        f"主题:{msg.get('subject','(无主题)')}\n"
        f"正文:\n{msg.get('body_text','')}"
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
        # 若你的端点不支持 response_format,删除下面一行,靠 SYSTEM_PROMPT + 解析兜底
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        async with httpx.AsyncClient(base_url=settings.llm_api_base, timeout=40) as c:
            r = await c.post("/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(_unwrap(content))
        out = {**_DEFAULT, **{k: data.get(k, _DEFAULT[k]) for k in _DEFAULT}}
        out["importance"] = int(out["importance"])
        out["model_used"] = settings.llm_model
        return out
    except Exception as e:
        d = dict(_DEFAULT)
        d["one_line"] = (msg.get("subject") or "")[:120]
        d["summary"] = f"(分析失败:{str(e)[:60]})"
        d["model_used"] = settings.llm_model
        return d


def _unwrap(s: str) -> str:
    """去掉可能的 ```json 包裹"""
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[4:] if s.lower().startswith("json") else s
    return s.strip()
```

> 可选两档(非必须、非路由框架):若想"便宜模型分级、贵模型只摘要重要邮件",再配一个 `SMART_MODEL` 端点,在 `importance >= summary_threshold` 时对这封追加一次摘要调用即可——两个直连调用 + 一个 `if`,不构成模型路由模块。默认先单模型。

### 5.6 日报(app/digest.py)

```python
from collections import defaultdict
from datetime import date

CATEGORY_ORDER = ["紧急·需回复", "金融·账户告警", "法律·合同", "重要通知", "订阅·营销", "社交其他"]


def render_markdown(day: str, rows: list) -> tuple[str, int, int]:
    """rows: list[(GmailMessage, AnalysisResult)];返回 (markdown, total, important)"""
    by_cat = defaultdict(list)
    for m, a in rows:
        by_cat[a.category].append((m, a))
    total = len(rows)
    important = sum(1 for _, a in rows if a.importance >= 4)

    out = [f"# {day} 邮件日报", "", f"共 {total} 封,其中需关注 {important} 封。", ""]
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        out.append(f"## {cat}({len(items)})")
        for m, a in sorted(items, key=lambda x: x[1].importance, reverse=True):
            out.append(f"- [{a.importance}] {a.one_line or m.subject} — {m.from_email}")
            if a.summary:
                out.append(f"  - {a.summary}")
        out.append("")
    return "\n".join(out), total, important
```

### 5.7 后台任务(app/jobs.py)

```python
import logging
from datetime import date, datetime, timedelta
from sqlalchemy import select

from app.db import SessionLocal
from app.models import GmailAccount, GmailMessage, AnalysisResult, DailyDigest
from app.config import settings
from app import gmail, prefilter, cleaner, analyzer, digest
from google.auth.exceptions import RefreshError

log = logging.getLogger("jobs")


def _sync_accounts_from_config(db) -> None:
    """把 .env 里的账号同步进库(以 email 为键,补新增、更新 token)"""
    for acc in settings.gmail_accounts:
        row = db.scalar(select(GmailAccount).where(GmailAccount.email == acc["email"]))
        if row:
            row.refresh_token = acc["refresh_token"]
            row.needs_reauth = False
        else:
            db.add(GmailAccount(email=acc["email"], refresh_token=acc["refresh_token"]))
    db.commit()


async def fetch_and_analyze() -> None:
    db = SessionLocal()
    try:
        _sync_accounts_from_config(db)
        accounts = db.scalars(select(GmailAccount).where(GmailAccount.is_active == True)).all()
        for acc in accounts:
            if acc.needs_reauth:
                continue
            try:
                svc = gmail.build_service(acc.refresh_token)
                messages, new_hid = gmail.fetch_new(svc, acc.last_history_id)
            except RefreshError:
                acc.needs_reauth = True               # invalid_grant:标记需重新授权
                db.commit()
                log.warning("account %s needs reauth", acc.email)
                continue
            except Exception as e:
                log.exception("fetch failed for %s: %s", acc.email, e)
                continue

            for msg in messages:
                # 去重:已存在则跳过
                exists = db.scalar(
                    select(GmailMessage.id).where(
                        GmailMessage.account_id == acc.id,
                        GmailMessage.message_id == msg["message_id"],
                    )
                )
                if exists:
                    continue

                filtered = prefilter.should_filter_out(msg)
                row = GmailMessage(
                    account_id=acc.id, message_id=msg["message_id"],
                    from_email=msg["from_email"], from_name=msg["from_name"],
                    subject=msg["subject"], received_at=msg["received_at"],
                    is_filtered=filtered,
                    body_text=cleaner.clean_body(msg["body_text"], msg["body_html"]),
                )
                db.add(row); db.flush()               # 拿到 row.id

                if not filtered:
                    res = await analyzer.analyze({
                        "from_email": msg["from_email"], "subject": msg["subject"],
                        "body_text": row.body_text,
                    })
                    db.add(AnalysisResult(
                        message_pk=row.id, category=res["category"], importance=res["importance"],
                        one_line=res["one_line"], summary=res["summary"], model_used=res["model_used"],
                    ))
                db.commit()

            acc.last_history_id = new_hid
            db.commit()
            log.info("synced %s: %d new", acc.email, len(messages))
    finally:
        db.close()


async def run_daily_digest() -> None:
    db = SessionLocal()
    try:
        day = date.today().isoformat()
        start = datetime.fromisoformat(day)
        end = start + timedelta(days=1)
        accounts = db.scalars(select(GmailAccount)).all()
        for acc in accounts:
            rows = db.execute(
                select(GmailMessage, AnalysisResult)
                .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
                .where(GmailMessage.account_id == acc.id,
                       GmailMessage.received_at >= start,
                       GmailMessage.received_at < end)
            ).all()
            md, total, important = digest.render_markdown(day, rows)
            existing = db.scalar(
                select(DailyDigest).where(DailyDigest.date == day, DailyDigest.account_id == acc.id)
            )
            if existing:
                existing.content_md, existing.total_emails, existing.important_emails = md, total, important
            else:
                db.add(DailyDigest(date=day, account_id=acc.id, content_md=md,
                                   total_emails=total, important_emails=important))
            db.commit()
    finally:
        db.close()
```

### 5.8 调度(app/scheduler.py)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.jobs import fetch_and_analyze, run_daily_digest

scheduler = AsyncIOScheduler(timezone=settings.timezone)


def start_scheduler() -> None:
    scheduler.add_job(fetch_and_analyze, "interval",
                      minutes=settings.fetch_interval_minutes,
                      id="fetch", max_instances=1, coalesce=True)
    scheduler.add_job(run_daily_digest, "cron",
                      hour=settings.digest_hour, minute=0, id="digest")
    scheduler.start()
```

---

## 6. 看板与认证(同服务渲染)

### 6.1 认证:无状态签名 Cookie(app/auth.py)

无需服务端会话存储,Railway 重启不掉登录。页面未登录跳 `/login`,API 未登录返回 401。

```python
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
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                            headers={"Location": "/login"})


def require_api(session: str | None = Cookie(default=None)):
    if not _valid(session):
        raise HTTPException(status_code=401, detail="not authenticated")
```

### 6.2 FastAPI 入口与路由(app/main.py)

```python
import logging
from datetime import date
from fastapi import FastAPI, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import GmailMessage, AnalysisResult, DailyDigest
from app.auth import make_cookie, require_page, require_api, COOKIE_NAME, _valid
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Gmail AI Analyzer", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CATEGORIES = ["紧急·需回复", "金融·账户告警", "法律·合同", "重要通知", "订阅·营销", "社交其他"]


@app.on_event("startup")
async def _startup():
    init_db()
    start_scheduler()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- 认证 ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(password: str = Form(...)):
    if password != settings.dashboard_password:
        return JSONResponse({"detail": "密码错误"}, status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, make_cookie(), max_age=settings.session_lifetime_days * 86400,
                    httponly=True, samesite="lax", secure=True)
    return resp


@app.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------- 看板页面(服务端渲染) ----------
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def dashboard(request: Request):
    db = SessionLocal()
    try:
        total = db.scalar(select(func.count(AnalysisResult.id))) or 0
        important = db.scalar(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.importance >= 4)
        ) or 0
        by_cat = dict(db.execute(
            select(AnalysisResult.category, func.count()).group_by(AnalysisResult.category)
        ).all())
        digests = db.scalars(select(DailyDigest).order_by(DailyDigest.date.desc()).limit(14)).all()
        return templates.TemplateResponse("dashboard.html", {
            "request": request, "total": total, "important": important,
            "by_cat": by_cat, "categories": CATEGORIES, "digests": digests,
        })
    finally:
        db.close()


@app.get("/emails", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def emails_page(
    request: Request,
    category: str = Query(""),
    importance: int = Query(0),
    date_from: str = Query(""),
    date_to: str = Query(""),
    page: int = Query(1, ge=1),
):
    db = SessionLocal()
    try:
        limit = 25
        q = (select(GmailMessage, AnalysisResult)
             .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id))
        if category:
            q = q.where(AnalysisResult.category == category)
        if importance:
            q = q.where(AnalysisResult.importance == importance)
        if date_from:
            q = q.where(GmailMessage.received_at >= date_from)
        if date_to:
            q = q.where(GmailMessage.received_at <= date_to + " 23:59:59")
        total = db.scalar(select(func.count()).select_from(q.subquery()))
        rows = db.execute(
            q.order_by(GmailMessage.received_at.desc()).limit(limit).offset((page - 1) * limit)
        ).all()
        return templates.TemplateResponse("emails.html", {
            "request": request, "rows": rows, "total": total, "page": page,
            "pages": max(1, -(-total // limit)), "categories": CATEGORIES,
            "f": {"category": category, "importance": importance,
                  "date_from": date_from, "date_to": date_to},
        })
    finally:
        db.close()


@app.get("/emails/{pk}", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def email_detail(request: Request, pk: int):
    db = SessionLocal()
    try:
        row = db.execute(
            select(GmailMessage, AnalysisResult)
            .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
            .where(GmailMessage.id == pk)
        ).first()
        if not row:
            raise HTTPException(404)
        m, a = row
        return templates.TemplateResponse("email_detail.html",
                                          {"request": request, "m": m, "a": a})
    finally:
        db.close()


@app.get("/digests", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digests_page(request: Request):
    db = SessionLocal()
    try:
        items = db.scalars(select(DailyDigest).order_by(DailyDigest.date.desc()).limit(90)).all()
        return templates.TemplateResponse("digests.html", {"request": request, "items": items})
    finally:
        db.close()


@app.get("/digests/{day}", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digest_detail(request: Request, day: str):
    db = SessionLocal()
    try:
        items = db.scalars(select(DailyDigest).where(DailyDigest.date == day)).all()
        return templates.TemplateResponse("digest_detail.html",
                                          {"request": request, "day": day, "items": items})
    finally:
        db.close()


# ---------- JSON API(同源,可选,供自动化/将来推送使用) ----------
@app.get("/api/emails", dependencies=[Depends(require_api)])
async def api_emails(limit: int = 20, offset: int = 0, category: str = "", importance: int = 0):
    db = SessionLocal()
    try:
        q = (select(GmailMessage, AnalysisResult)
             .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id))
        if category:
            q = q.where(AnalysisResult.category == category)
        if importance:
            q = q.where(AnalysisResult.importance == importance)
        rows = db.execute(q.order_by(GmailMessage.received_at.desc())
                          .limit(limit).offset(offset)).all()
        return {"items": [{
            "id": m.id, "from": m.from_email, "subject": m.subject,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "category": a.category, "importance": a.importance, "one_line": a.one_line,
        } for m, a in rows]}
    finally:
        db.close()
```

### 6.3 模板(templates/,Jinja2)

`base.html`(外壳 + 导航 + 登出):

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}邮件分析{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <a href="/" class="brand">📧 邮件分析</a>
    <nav>
      <a href="/">概览</a>
      <a href="/emails">邮件</a>
      <a href="/digests">日报</a>
      <form action="/logout" method="post" style="display:inline">
        <button class="link">登出</button>
      </form>
    </nav>
  </header>
  <main class="container">{% block body %}{% endblock %}</main>
</body>
</html>
```

`login.html`:

```html
{% extends "base.html" %}
{% block body %}
<div class="login-card">
  <h1>登录看板</h1>
  <form id="f" method="post" action="/login">
    <input type="password" name="password" placeholder="密码" required autofocus>
    <button type="submit">登录</button>
  </form>
  <p id="err" class="err"></p>
</div>
<script>
  // 用 fetch 提交以便显示错误(POST /login 成功会 303 跳转)
  document.getElementById('f').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const r = await fetch('/login', {method:'POST', body:fd, redirect:'follow'});
    if (r.redirected) { location.href = r.url; }
    else { document.getElementById('err').textContent = '密码错误'; }
  });
</script>
{% endblock %}
```

`emails.html`(筛选表单 + 列表 + 分页;GET 提交,无需 JS 状态):

```html
{% extends "base.html" %}
{% block body %}
<h1>邮件列表</h1>
<form class="filters" method="get" action="/emails">
  <select name="category">
    <option value="">全部分类</option>
    {% for c in categories %}
      <option value="{{c}}" {% if f.category==c %}selected{% endif %}>{{c}}</option>
    {% endfor %}
  </select>
  <select name="importance">
    <option value="0">全部重要度</option>
    {% for i in [5,4,3,2,1] %}
      <option value="{{i}}" {% if f.importance==i %}selected{% endif %}>Level {{i}}</option>
    {% endfor %}
  </select>
  <input type="date" name="date_from" value="{{f.date_from}}">
  <input type="date" name="date_to" value="{{f.date_to}}">
  <button type="submit">筛选</button>
</form>

<p class="muted">共 {{total}} 封</p>
<ul class="email-list">
  {% for m, a in rows %}
  <li class="email">
    <a href="/emails/{{m.id}}">
      <div class="row1">
        <span class="subject">{{a.one_line or m.subject}}</span>
        <span class="imp imp{{a.importance}}">{{a.importance}}</span>
      </div>
      <div class="row2">
        <span class="cat">{{a.category}}</span>
        <span class="from">{{m.from_email}}</span>
        <span class="time">{{m.received_at}}</span>
      </div>
    </a>
  </li>
  {% endfor %}
</ul>

<nav class="pager">
  {% if page>1 %}<a href="?category={{f.category}}&importance={{f.importance}}&date_from={{f.date_from}}&date_to={{f.date_to}}&page={{page-1}}">← 上一页</a>{% endif %}
  <span>第 {{page}} / {{pages}} 页</span>
  {% if page<pages %}<a href="?category={{f.category}}&importance={{f.importance}}&date_from={{f.date_from}}&date_to={{f.date_to}}&page={{page+1}}">下一页 →</a>{% endif %}
</nav>
{% endblock %}
```

`email_detail.html`:

```html
{% extends "base.html" %}
{% block body %}
<a href="/emails" class="muted">← 返回</a>
<article class="detail">
  <h1>{{m.subject}}</h1>
  <div class="meta">发件人:{{m.from_email}} · {{m.received_at}}</div>
  <div class="badges">
    <span class="cat">{{a.category}}</span>
    <span class="imp imp{{a.importance}}">重要度 {{a.importance}}</span>
  </div>
  <p class="oneline"><b>摘要:</b>{{a.one_line}}</p>
  {% if a.summary %}<div class="summary"><b>要点:</b><p>{{a.summary}}</p></div>{% endif %}
  <h2>正文</h2>
  <pre class="body">{{m.body_text}}</pre>
</article>
{% endblock %}
```

`dashboard.html` / `digests.html` / `digest_detail.html` 结构同上(`dashboard.html` 展示统计卡片 + 分类计数 + 最近日报链接;`digests.html` 列出日报;`digest_detail.html` 把 `content_md` 直接以 `<pre>` 或经 Markdown 渲染展示)。这些模板与上面同一套写法,实施时照搬。

`static/style.css` 给一套简洁深色样式即可(卡片、列表、重要度色阶 `imp4/imp5` 标红),无第三方依赖。

---

## 7. 配置与环境变量

`.env.example`:

```bash
# ===== Google OAuth 客户端(刷新 token 用,来自 GCP OAuth 客户端·Desktop 类型)=====
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx

# ===== Gmail 账号(每个邮箱两行,编号从 1 递增)=====
GMAIL_EMAIL_1=you1@gmail.com
GMAIL_REFRESH_TOKEN_1=1//0gK...
GMAIL_EMAIL_2=you2@gmail.com
GMAIL_REFRESH_TOKEN_2=1//0gK...

# ===== 固定模型(OpenAI 兼容)=====
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
# 也可指向 DeepSeek / 本地兼容网关等任意 OpenAI 兼容端点

# ===== 看板认证 =====
DASHBOARD_PASSWORD=换成你的强密码
SECRET_KEY=用随机长串(如 openssl rand -hex 32 生成)
SESSION_LIFETIME_DAYS=7

# ===== 行为参数 =====
FETCH_INTERVAL_MINUTES=5
DIGEST_HOUR=8
TZ=Asia/Singapore
BACKFILL_DAYS=2
BODY_MAX_CHARS=2000
IMPORTANCE_SUMMARY_THRESHOLD=4

# ===== 预过滤(逗号分隔,可留空)=====
WHITELIST_FROM=boss@company.com,broker@
BLACKLIST_FROM=noreply@spam.com

# ===== 存储(默认 SQLite 挂卷;如用 Railway Postgres 改这里)=====
DATABASE_URL=sqlite:////app/data/app.db
```

`requirements.txt`:

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
jinja2==3.1.4
itsdangerous==2.2.0
python-multipart==0.0.9
sqlalchemy==2.0.30
apscheduler==3.10.4
httpx==0.27.0
beautifulsoup4==4.12.3
google-auth==2.30.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.134.0
psycopg[binary]==3.1.19    # 仅用 PostgreSQL 时需要
tzdata==2024.1
```

---

## 8. 一次性授权:换取 refresh_token(scripts/authorize.py)

前提:在 GCP 建项目 → 启用 Gmail API → 建 OAuth 客户端(类型 **Desktop app**)→ 下载 `client_secret.json` → **OAuth 同意屏幕发布为 Production**(个人用<100、免验证;首次会让你点掉一次"未验证应用"警告)。否则 refresh token 会 7 天失效。

```python
# 本地运行:python scripts/authorize.py
# 浏览器弹出授权,选要接入的那个 Gmail,完成后控制台打印 refresh_token 与 email
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=8765, access_type="offline", prompt="consent")
svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
email = svc.users().getProfile(userId="me").execute()["emailAddress"]

print("EMAIL          =", email)
print("REFRESH_TOKEN  =", creds.refresh_token)
print("\n把上面两行写进 .env / Railway 变量:GMAIL_EMAIL_N / GMAIL_REFRESH_TOKEN_N")
```

每个 Gmail 账号跑一次(浏览器切到对应账号授权)。`access_type=offline` + `prompt=consent` 确保返回 refresh_token。

---

## 9. 部署(Railway 单服务)

### 9.1 Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.2 railway.toml

```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
healthcheckPath = "/health"
restartPolicyType = "always"

# SQLite 持久化卷
[[volumes]]
mountPath = "/app/data"
```

> 无需 Railway 外部 cron——拉取与日报由进程内 APScheduler 触发。Railway 服务常驻不缩容,调度可靠。

### 9.3 部署步骤

1. 本地跑 `scripts/authorize.py` 拿到每个 Gmail 的 `email + refresh_token`。
2. GitHub 推送代码(勿提交 `client_secret.json` / `.env`)。
3. Railway → New Project → 关联该 repo,自动按 Dockerfile 构建。
4. Railway → Variables:粘贴 `.env` 全部变量(含 `GOOGLE_CLIENT_ID/SECRET`、各 `GMAIL_*`、`LLM_*`、`DASHBOARD_PASSWORD`、`SECRET_KEY`)。
5. Railway → Volumes:挂载 `/app/data`(SQLite 持久化)。
6. 部署完成后访问服务域名 `/login`,用 `DASHBOARD_PASSWORD` 登录。
7. 等首次 `fetch_and_analyze` 跑完(或在 Logs 观察),看板即有数据。

---

## 10. MVP 与分期

**MVP(第一阶段,本方案即覆盖)**:多 Gmail 只读增量拉取 → 预过滤 → 固定模型分级+摘要 → 写库 → 每日日报 → 密码登录看板(概览/邮件筛选/详情/日报)。

**第二阶段**:起草回复(`SMART_MODEL`);日报推送(飞书卡片复用 doc-page / 邮件);写回 Gmail 标签或自动折叠营销(加 `gmail.modify`);全文搜索(SQLite FTS5);附件解析(PDF 对账单抽数字);自定义规则页面。

---

## 11. 常见问题与排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 某账号无新数据且日志 `needs reauth` | refresh token 失效(改密码/6 月未用/撤销/Testing 模式 7 天) | 重跑 `authorize.py`,更新该账号 `GMAIL_REFRESH_TOKEN_N`;确认 OAuth 应用是 Production |
| 首次拉取量异常大/小 | `BACKFILL_DAYS` 设置 | 调 `BACKFILL_DAYS`;首次引导后转增量 |
| `history.list` 报 404 | `historyId` 过期(Gmail 仅保留有限历史) | 已内置:自动全量回退并重置水位,无需干预 |
| 模型返回非 JSON 解析失败 | 端点不支持 `response_format` 或模型不守约 | 删 `response_format` 行,依赖 prompt + `_unwrap` 兜底;失败该封下轮重试 |
| 登录后仍跳回 `/login` | Cookie 未被接受 | 确认走 HTTPS(Railway 默认是)、`secure=True`、`SECRET_KEY` 已设 |
| 重启后要重新登录 | 误用了内存 session | 本方案用签名 Cookie,不应发生;检查 `SECRET_KEY` 是否每次部署都变(应固定) |
| 邮件重复分析 | 去重失效 | `(account_id, message_id)` 唯一约束 + 写库前查重已保证;确认每轮成功后更新 `last_history_id` |

---

## 12. 给 Coding Plan 的实施清单(按顺序)

1. 脚手架:目录树 + `requirements.txt` + `.env.example` + `Dockerfile` + `railway.toml`。
2. 数据层:`models.py`(ORM)+ `db.py`(引擎/建表)。
3. `config.py`:环境变量解析(账号编号循环、规则列表)。
4. Gmail:`gmail.py`(刷新、MIME 递归解析、引导 backfill、history 增量、404 回退)。
5. 处理链:`prefilter.py` + `cleaner.py` + `analyzer.py`(OpenAI 兼容直连 + JSON 兜底)。
6. 任务与调度:`jobs.py`(拉取+日报)+ `scheduler.py`(APScheduler)。
7. 认证:`auth.py`(签名 Cookie,页面跳转/API 401 两个依赖)。
8. 看板:`main.py` 路由 + `templates/*`(先做 `base/login/emails/email_detail`,再补 `dashboard/digests/digest_detail`)+ `static/style.css`。
9. 授权脚本:`scripts/authorize.py`。
10. 自测:本地 `uvicorn` 跑起,放一两个真实 Gmail 验证拉取→分级→看板→日报闭环。

**可全权交给 AI**:以上 1–6、8(模板/样式)、9。**需你把关**:分类口径与重要度阈值(`SYSTEM_PROMPT` / `IMPORTANCE_SUMMARY_THRESHOLD`)、固定模型选型、`DASHBOARD_PASSWORD`/`SECRET_KEY`/各 refresh token 的密钥安全。

---

## 附:如果你坚持要独立 Next.js 看板(可选,不推荐用于本场景)

把 `main.py` 的页面路由删除,只保留 `/api/*`(改为返回 JSON、认证用 `require_api`),前端用 Next.js 部署 Cloudflare Pages,后端加 CORS 允许该前端域名、Cookie 用 `SameSite=None; Secure`。代价是:多一个部署目标、跨域 Cookie 配置、CORS 维护。对单用户个人工具收益不大,故本方案默认同服务渲染。

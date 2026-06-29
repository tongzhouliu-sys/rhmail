---
title: Gmail 个人 AI 邮件分析系统 — 技术开发方案
version: v0.2-dev
updated: 2026-06-29
audience: 开发者 / AI Coding Plan
---

# Gmail 个人 AI 邮件分析系统 — 技术开发方案

> 基于精简版框架(v0.2),给开发者/AI 的完整技术文档。包含项目骨架、模块设计、API 接口定义、配置与部署。

---

## 1. 概述

### 1.1 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 语言 | Python 3.10+ | 核心逻辑 |
| 框架 | FastAPI | Web 服务 + API endpoint |
| 异步 | asyncio | Gmail API 调用并发 |
| Gmail 接入 | google-api-python-client | 官方 SDK(增量拉取 + History API) |
| 模型调用 | httpx / openai-python / requests | 直连固定模型 API |
| 存储 | SQLite(开发) / PostgreSQL(Railway) | 邮件元数据 + 分析结果 |
| 定时 | Railway Cron(生产) / APScheduler(本地) | 两条定时任务:拉取 + 日报 |
| 前端(可选) | Markdown / 飞书卡片(JSON) | 日报渲染与推送 |
| 部署 | Docker + Railway | 一个服务 + 环境变量 + cron |

### 1.2 核心架构(文字版)

```
[Gmail 账号 1, 2, 3...]
  ↓ (History API,增量)
[Fetcher] → 逐邮箱拉新邮件(message ID + headers + parsed body)
  ↓
[Prefilter] → 规则粗筛(List-Unsubscribe / 发件人白黑名单 / 正则)
  ↓ (丢弃噪声)
[Cleaner] → HTML→文本 + 去引用/签名 + 按长度截断
  ↓
[Analyzer] → 调固定模型 API(结构化:分类+重要度+一句话+摘要)
  ↓ (JSON 返回)
[Store] → 写 DB(message_id 去重,不重复分析)
  ↓
[Digest Cron] → 聚合当日结果 → 生成日报 → 推送
```

---

## 2. 快速开始

### 2.1 前置条件

- Python 3.10+
- Gmail 账号 × N(已授权 OAuth,Production 发布)
- 固定模型 API(OpenAI 格式或直连格式):OpenAI、Anthropic、DeepSeek、Gemini 等之一
- Railway CLI(生产部署用)或本地 Docker

### 2.2 本地开发环境

```bash
# 克隆 / 新建项目
mkdir gmail-ai && cd gmail-ai
git init

# 虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依赖(见 3.1 requirements.txt)
pip install -r requirements.txt

# 复制 .env.example → .env,填入你的密钥
cp .env.example .env
# 填 GMAIL_REFRESH_TOKEN_1, GMAIL_REFRESH_TOKEN_2, ...
# 填 LLM_API_BASE, LLM_API_KEY, LLM_MODEL

# 初始化数据库
python scripts/init_db.py

# 本地跑(带 APScheduler 定时,测试用)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2.3 第一个邮件拉取(CLI 测试)

```bash
# 一次性拉取 Gmail 1 的新邮件
python -m app.tasks.fetch --gmail-index 1 --dry-run

# 输出形如:
# Fetched 5 new messages from gmail1@gmail.com
# Message: from=john@example.com, subject=Project Status, importance=4

# 不加 --dry-run 则实际写 DB
python -m app.tasks.fetch --gmail-index 1
```

---

## 3. 项目结构

### 3.1 目录树

```
gmail-ai/
├── requirements.txt              # 依赖清单
├── .env.example                  # 环境变量模板
├── docker/
│   ├── Dockerfile                # Railway 部署镜像
│   └── railway.toml              # Railway 配置(cron、环境变量、卷)
├── scripts/
│   ├── init_db.py                # 初始化 SQLite / PG,建表
│   └── migrate_db.py             # 数据库迁移(二期)
├── app/
│   ├── main.py                   # FastAPI app 入口;可选只读日报 endpoint
│   ├── config.py                 # 环境变量解析、模型参数、日志
│   ├── models.py                 # Pydantic 数据类(Email, Analysis, 等)
│   ├── db.py                     # SQLite / PG 连接、session 管理
│   ├── modules/
│   │   ├── fetcher.py            # Gmail 增量拉取(History API)
│   │   ├── prefilter.py          # 规则预过滤(List-Unsubscribe/白黑名单)
│   │   ├── cleaner.py            # HTML→文本、去噪、截断
│   │   ├── analyzer.py           # 调固定模型 API,返回分类+摘要
│   │   └── digest.py             # 日报聚合、渲染(Markdown/飞书)
│   ├── tasks/
│   │   ├── __main__.py           # CLI 入口(python -m app.tasks ...)
│   │   ├── fetch.py              # Cron 拉取任务(或被 Railway Cron 直接调)
│   │   └── digest.py             # Cron 日报任务
│   └── utils/
│       ├── gmail_oauth.py        # OAuth token 刷新、增量逻辑
│       ├── llm_client.py         # 模型 API 直连(wrapper)
│       └── text_clean.py         # HTML 清洗工具函数
└── tests/
    ├── test_fetcher.py
    ├── test_analyzer.py
    └── ...
```

### 3.2 依赖清单(requirements.txt)

```
fastapi==0.104.0
uvicorn[standard]==0.24.0
google-auth==2.25.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.100.0
httpx==0.25.0
openai==1.3.0  # 若用 OpenAI 或兼容格式
pydantic==2.5.0
pydantic-settings==2.1.0
sqlalchemy==2.0.0
psycopg[binary]==3.1.0  # PostgreSQL 驱动(本地可不装)
python-dotenv==1.0.0
beautifulsoup4==4.12.0  # HTML 清洗
markdownify==0.11.0     # HTML→Markdown
lxml==4.9.0
aiofiles==23.2.0
aiohttp==3.9.0
```

---

## 4. 核心模块设计

### 4.1 数据模型(models.py)

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# ===== Gmail 相关 =====
class GmailAccount(BaseModel):
    """Gmail 账号信息(存 DB)"""
    id: int
    email: str
    refresh_token: str
    last_history_id: str  # 用于增量同步
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

class GmailMessage(BaseModel):
    """原始邮件数据(存 DB)"""
    id: int
    gmail_account_id: int
    message_id: str  # Gmail 内部 ID,用于去重
    from_email: str
    from_name: Optional[str]
    subject: str
    body_text: str  # HTML 清洗后的纯文本
    body_snippet: str  # Gmail 返回的 snippet(备用)
    received_at: datetime
    is_filtered: bool  # 预过滤标志(True=已丢弃)
    created_at: datetime

# ===== 分析结果 =====
class AnalysisResult(BaseModel):
    """AI 模型分析结果(存 DB)"""
    id: int
    message_id: int  # FK to GmailMessage
    category: str  # 紧急·需回复 | 金融·账户告警 | ... 
    importance: int  # 1-5
    one_line: str  # 一句话总结(中文)
    summary: Optional[str]  # 详细摘要(中文)
    model_used: str  # 记录用了哪个模型
    tokens_used: Optional[int]  # (可选)调试用
    processed_at: datetime
    created_at: datetime

class DailyDigest(BaseModel):
    """日报(存 DB/生成时用)"""
    id: int
    date: str  # YYYY-MM-DD
    gmail_account_id: int
    total_emails: int
    important_emails: int
    digest_content: str  # Markdown / JSON(飞书卡片)
    digest_format: str  # markdown | feishu
    sent_at: Optional[datetime]
    created_at: datetime
```

### 4.2 Fetcher(增量拉取)

```python
# app/modules/fetcher.py
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import Request
from googleapiclient.discovery import build
import asyncio

class GmailFetcher:
    """Gmail 增量拉取:用 History API 只处理新邮件"""
    
    def __init__(self, gmail_account: GmailAccount):
        self.account = gmail_account
        self.service = self._build_service()
    
    def _build_service(self):
        """从 refresh_token 刷新 access_token 并建立 service"""
        # 使用 google-auth-oauthlib 或直接 refresh flow
        credentials = self._refresh_access_token()
        return build('gmail', 'v1', credentials=credentials)
    
    async def fetch_new_messages(self) -> list[dict]:
        """
        从 last_history_id 拉新邮件。
        
        返回格式:
        [
          {
            "message_id": "18b5...",
            "from": "john@example.com",
            "subject": "Re: Project",
            "body_raw": "<html>...</html>",
            "received_at": "2026-06-29T10:30:00Z"
          },
          ...
        ]
        """
        history_id = int(self.account.last_history_id)
        
        # 调 History API
        history = self.service.users().history().list(
            userId='me',
            startHistoryId=history_id,
            historyTypes=['messageAdded']
        ).execute()
        
        new_messages = []
        for item in history.get('history', []):
            for msg in item.get('messagesAdded', []):
                message_id = msg['message']['id']
                msg_data = self._get_message_full(message_id)
                new_messages.append(msg_data)
        
        # 更新 last_history_id
        latest_id = history.get('historyId')
        if latest_id:
            self.account.last_history_id = latest_id
            db.update_account(self.account)
        
        return new_messages
    
    def _get_message_full(self, message_id: str) -> dict:
        """获取完整邮件(headers + body)"""
        msg = self.service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        body_text = self._extract_body(msg['payload'])
        
        return {
            'message_id': message_id,
            'from': headers.get('From', 'unknown'),
            'subject': headers.get('Subject', '(no subject)'),
            'body_raw': body_text,
            'received_at': headers.get('Date', ''),
            'list_unsubscribe': headers.get('List-Unsubscribe', '')
        }
    
    def _extract_body(self, payload) -> str:
        """递归提取邮件 body(处理 multipart)"""
        # 简化版:返回纯文本或 HTML
        if payload.get('mimeType') == 'text/plain':
            return payload['parts'][0]['body'].get('data', '')
        elif payload.get('mimeType') == 'text/html':
            return payload['parts'][1]['body'].get('data', '')
        else:
            # multipart/alternative,取第一个 part
            for part in payload.get('parts', []):
                if part['mimeType'] in ['text/plain', 'text/html']:
                    return part['body'].get('data', '')
        return ''
    
    def _refresh_access_token(self) -> Credentials:
        """用 refresh_token 换 access_token"""
        # 伪代码,实际用 google-auth-oauthlib
        # 或直接 HTTP POST to https://oauth2.googleapis.com/token
        pass
```

### 4.3 Prefilter(规则粗筛)

```python
# app/modules/prefilter.py
import re
from typing import Optional

class EmailPrefilter:
    """规则预过滤:List-Unsubscribe/白黑名单/正则"""
    
    def __init__(self, config):
        self.whitelist_from = config.get('whitelist_from', [])  # 白名单发件人
        self.blacklist_from = config.get('blacklist_from', [])  # 黑名单
        self.blacklist_subject = config.get('blacklist_subject', [])  # 主题黑名单
    
    def should_filter_out(self, message: dict) -> bool:
        """
        返回 True 表示丢弃(进不了 LLM)。
        
        优先级:
        1. 白名单内 → 不过滤
        2. 黑名单内 → 过滤
        3. List-Unsubscribe 头 → 过滤(营销邮件)
        4. 主题黑名单正则 → 过滤
        """
        from_email = message.get('from', '').lower()
        subject = message.get('subject', '').lower()
        list_unsubscribe = message.get('list_unsubscribe', '')
        
        # 白名单优先
        if any(wl in from_email for wl in self.whitelist_from):
            return False
        
        # 黑名单
        if any(bl in from_email for bl in self.blacklist_from):
            return True
        
        # List-Unsubscribe(营销/订阅邮件特征)
        if list_unsubscribe:
            return True
        
        # 主题黑名单正则
        for pattern in self.blacklist_subject:
            if re.search(pattern, subject):
                return True
        
        return False  # 不过滤,进 LLM
```

### 4.4 Cleaner(HTML 清洗 + 截断)

```python
# app/modules/cleaner.py
from bs4 import BeautifulSoup
import re

class TextCleaner:
    """HTML→文本、去引用/签名/页脚、按长度截断"""
    
    def __init__(self, max_length: int = 2000):
        self.max_length = max_length
    
    def clean(self, html_or_text: str) -> str:
        """
        返回清洁后的文本(UTF-8)。
        
        步骤:
        1. HTML 转纯文本(BeautifulSoup)
        2. 去引用历史(Gmail 样式:'>' 开头行)
        3. 去签名(常见模式)
        4. 按长度截断
        """
        # 1. HTML→文本
        text = self._html_to_text(html_or_text)
        
        # 2. 去引用
        text = self._remove_quotes(text)
        
        # 3. 去签名
        text = self._remove_signature(text)
        
        # 4. 截断
        if len(text) > self.max_length:
            text = text[:self.max_length] + '...'
        
        return text.strip()
    
    def _html_to_text(self, html: str) -> str:
        """HTML 解析转纯文本"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            # 去掉脚本、样式
            for script in soup(['script', 'style']):
                script.decompose()
            text = soup.get_text(separator='\n')
            return text
        except:
            return html  # fallback
    
    def _remove_quotes(self, text: str) -> str:
        """去掉引用的邮件历史(以 '>' 开头的行)"""
        lines = text.split('\n')
        filtered = [l for l in lines if not l.strip().startswith('>')]
        return '\n'.join(filtered)
    
    def _remove_signature(self, text: str) -> str:
        """去掉常见签名(以 '--' 或 '___' 分割)"""
        if '--\n' in text:
            text = text.split('--\n')[0]
        if '___\n' in text:
            text = text.split('___\n')[0]
        return text
```

### 4.5 Analyzer(模型调用)

```python
# app/modules/analyzer.py
import httpx
import json
from app.config import settings

class EmailAnalyzer:
    """调固定模型 API(结构化调用)"""
    
    def __init__(self):
        self.api_base = settings.LLM_API_BASE
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
    
    async def analyze(self, message: dict) -> dict:
        """
        调模型分析邮件。
        
        输入:
        {
          'from': 'john@example.com',
          'subject': 'Project Status',
          'body': '...cleaned text...'
        }
        
        输出:
        {
          'category': '紧急·需回复',
          'importance': 4,
          'one_line': 'John 发来项目进度报告',
          'summary': '项目已完成 60%,延期原因是...'
        }
        """
        
        prompt = self._build_prompt(message)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f'{self.api_base}/chat/completions',
                    json={
                        'model': self.model,
                        'messages': [
                            {
                                'role': 'system',
                                'content': self._system_prompt()
                            },
                            {
                                'role': 'user',
                                'content': prompt
                            }
                        ],
                        'temperature': 0.3,
                        'max_tokens': 500
                    },
                    headers={
                        'Authorization': f'Bearer {self.api_key}',
                        'Content-Type': 'application/json'
                    },
                    timeout=30.0
                )
            
            response.raise_for_status()
            result = response.json()
            
            # 解析 LLM 返回的 JSON
            content = result['choices'][0]['message']['content']
            try:
                analysis = json.loads(content)
            except json.JSONDecodeError:
                # fallback:解析失败则给默认值
                analysis = {
                    'category': '社交其他',
                    'importance': 2,
                    'one_line': message.get('subject', ''),
                    'summary': ''
                }
            
            return analysis
        
        except Exception as e:
            # 调用失败:返回默认值,下轮重试
            print(f'Analyzer error: {e}')
            return {
                'category': '社交其他',
                'importance': 1,
                'one_line': message.get('subject', ''),
                'summary': f'分析失败(错误:{str(e)[:50]})'
            }
    
    def _system_prompt(self) -> str:
        """系统提示(分类规则)"""
        return """你是一个邮件分析助手。分析邮件并返回 JSON:
{
  "category": "紧急·需回复 | 金融·账户告警 | 法律·合同 | 重要通知 | 订阅·营销 | 社交其他",
  "importance": 1-5(1=最低,5=最高),
  "one_line": "一句话总结邮件内容(中文)",
  "summary": "重要度>=4 时给要点(日期/金额/待办),否则留空"
}

分类规则:
- 紧急·需回复:个人/工作直发、含截止日期或明确问句
- 金融·账户告警:券商、保证金、对账单等账户相关
- 法律·合同:律所、法院、合同、传票、仲裁
- 重要通知:学校、政府、银行账户安全、OTP
- 订阅·营销:包含 List-Unsubscribe 头(已过滤)或明显营销特征
- 社交其他:其余

返回**纯 JSON**,无其他文字。"""
    
    def _build_prompt(self, message: dict) -> str:
        """构建用户 prompt"""
        return f"""分析这封邮件:

发件人:{message.get('from', '?')}
主题:{message.get('subject', '(无主题)')}
内容:
{message.get('body', '')}"""
```

### 4.6 Digest(日报聚合)

```python
# app/modules/digest.py
from datetime import datetime, date
from collections import defaultdict

class DailyDigest:
    """日报聚合与渲染"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def generate(self, gmail_account_id: int, date_str: str = None) -> dict:
        """
        生成日报。
        
        date_str: YYYY-MM-DD,默认今天
        返回:{'format': 'markdown'|'feishu', 'content': '...'}
        """
        if not date_str:
            date_str = date.today().isoformat()
        
        # 查询当日分析结果
        analyses = self.db.query(AnalysisResult).join(GmailMessage).filter(
            GmailMessage.gmail_account_id == gmail_account_id,
            GmailMessage.received_at >= f'{date_str} 00:00:00',
            GmailMessage.received_at < f'{date_str} 23:59:59'
        ).all()
        
        # 按分类聚合
        by_category = defaultdict(list)
        for a in analyses:
            by_category[a.category].append(a)
        
        # 生成 Markdown
        md = self._render_markdown(by_category, date_str)
        
        return {
            'format': 'markdown',
            'content': md
        }
    
    def _render_markdown(self, by_category: dict, date_str: str) -> str:
        """渲染为 Markdown"""
        lines = [f'# {date_str} 邮件日报']
        lines.append('')
        
        total = sum(len(v) for v in by_category.values())
        important = sum(1 for v in by_category.values() for a in v if a.importance >= 4)
        lines.append(f'📊 总计:{total} 封邮件,其中 {important} 封需关注')
        lines.append('')
        
        # 优先展示高优先级分类
        category_order = [
            '紧急·需回复',
            '金融·账户告警',
            '法律·合同',
            '重要通知',
            '订阅·营销',
            '社交其他'
        ]
        
        for cat in category_order:
            if cat not in by_category:
                continue
            
            items = by_category[cat]
            lines.append(f'## {cat}({len(items)})')
            
            for a in items:
                lines.append(f'- **{a.one_line}** (重要度:{a.importance})')
                if a.summary:
                    lines.append(f'  {a.summary}')
            
            lines.append('')
        
        return '\n'.join(lines)
```

---

## 5. 配置与环境变量

### 5.1 .env.example

```bash
# ===== Gmail 账号(每个一行) =====
GMAIL_REFRESH_TOKEN_1=1//0gKfv...
GMAIL_ACCOUNT_1=your-email-1@gmail.com
GMAIL_REFRESH_TOKEN_2=1//0gKfv...
GMAIL_ACCOUNT_2=your-email-2@gmail.com
# ... 更多账号

# ===== 固定模型 API =====
LLM_API_BASE=https://api.openai.com/v1  # OpenAI / 兼容 API
LLM_API_KEY=sk-...
LLM_MODEL=gpt-3.5-turbo
# 或:
# LLM_API_BASE=https://api.anthropic.com
# LLM_API_KEY=sk-ant-...
# LLM_MODEL=claude-3-haiku-20240307

# ===== 存储 =====
DATABASE_URL=sqlite:///./gmail_ai.db  # 本地开发
# 或 PostgreSQL(Railway):
# DATABASE_URL=postgresql://user:pass@localhost/gmail_ai

# ===== 日报推送 =====
DIGEST_FORMAT=markdown  # markdown | feishu
DIGEST_SCHEDULE_HOUR=8  # 每天 8 点推送

# ===== 拉取周期 =====
FETCH_INTERVAL_MINUTES=5  # 每 5 分钟拉一次

# ===== 日志 =====
LOG_LEVEL=INFO
```

### 5.2 config.py

```python
from pydantic_settings import BaseSettings
import logging

class Settings(BaseSettings):
    """环境变量解析"""
    
    # Gmail
    gmail_accounts: dict = {}  # {1: {'email': '...', 'refresh_token': '...'}}
    
    # Model
    llm_api_base: str
    llm_api_key: str
    llm_model: str
    
    # Database
    database_url: str = 'sqlite:///./gmail_ai.db'
    
    # Digest
    digest_format: str = 'markdown'
    digest_schedule_hour: int = 8
    
    # Fetch
    fetch_interval_minutes: int = 5
    
    # Log
    log_level: str = 'INFO'
    
    class Config:
        env_file = '.env'
    
    def __init__(self, **data):
        super().__init__(**data)
        # 解析 GMAIL_ACCOUNT_N, GMAIL_REFRESH_TOKEN_N
        import os
        for key in os.environ:
            if key.startswith('GMAIL_ACCOUNT_'):
                idx = key.split('_')[-1]
                email = os.environ.get(f'GMAIL_ACCOUNT_{idx}')
                token = os.environ.get(f'GMAIL_REFRESH_TOKEN_{idx}')
                if email and token:
                    self.gmail_accounts[int(idx)] = {
                        'email': email,
                        'refresh_token': token
                    }

settings = Settings()
logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level)
```

---

## 6. 数据库(SQLite / PostgreSQL)

### 6.1 表结构

```sql
-- Gmail 账号
CREATE TABLE gmail_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    refresh_token TEXT NOT NULL,
    last_history_id VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 原始邮件
CREATE TABLE gmail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_account_id INTEGER NOT NULL,
    message_id VARCHAR(255) UNIQUE NOT NULL,  -- Gmail 内部 ID(用于去重)
    from_email VARCHAR(255),
    from_name VARCHAR(255),
    subject TEXT,
    body_text TEXT,
    body_snippet TEXT,
    received_at TIMESTAMP,
    is_filtered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gmail_account_id) REFERENCES gmail_accounts(id)
);

CREATE INDEX idx_message_id ON gmail_messages(message_id);
CREATE INDEX idx_received_at ON gmail_messages(received_at);

-- 分析结果
CREATE TABLE analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    category VARCHAR(50),
    importance INTEGER,  -- 1-5
    one_line TEXT,
    summary TEXT,
    model_used VARCHAR(100),
    tokens_used INTEGER,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES gmail_messages(id)
);

CREATE INDEX idx_category ON analysis_results(category);
CREATE INDEX idx_importance ON analysis_results(importance);

-- 日报
CREATE TABLE daily_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE UNIQUE,
    gmail_account_id INTEGER NOT NULL,
    total_emails INTEGER,
    important_emails INTEGER,
    digest_content TEXT,
    digest_format VARCHAR(20),  -- markdown | feishu
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gmail_account_id) REFERENCES gmail_accounts(id)
);
```

### 6.2 初始化脚本(scripts/init_db.py)

```python
from sqlalchemy import create_engine, text
from app.config import settings

def init_db():
    """初始化数据库表"""
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        # 直接执行上面的 SQL(或用 SQLAlchemy ORM 的 create_all)
        sql = open('scripts/schema.sql').read()
        for stmt in sql.split(';'):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.commit()
    
    print('Database initialized.')

if __name__ == '__main__':
    init_db()
```

---

## 7. 定时任务(Cron)

### 7.1 拉取任务(app/tasks/fetch.py)

```python
import asyncio
from app.modules.fetcher import GmailFetcher
from app.modules.prefilter import EmailPrefilter
from app.modules.cleaner import TextCleaner
from app.modules.analyzer import EmailAnalyzer
from app.db import get_session
from app.config import settings

async def fetch_and_analyze():
    """Cron 拉取并分析所有 Gmail 账号"""
    
    db = get_session()
    prefilter = EmailPrefilter(config={})
    cleaner = TextCleaner()
    analyzer = EmailAnalyzer()
    
    for idx, account_info in settings.gmail_accounts.items():
        try:
            # 拉取
            fetcher = GmailFetcher(account_info)
            messages = await fetcher.fetch_new_messages()
            
            for msg in messages:
                # 预过滤
                if prefilter.should_filter_out(msg):
                    # 写 DB 标记为过滤
                    db.write_message(msg, is_filtered=True)
                    continue
                
                # 清洗
                cleaned_body = cleaner.clean(msg['body_raw'])
                
                # 分析
                analysis = await analyzer.analyze({
                    'from': msg['from'],
                    'subject': msg['subject'],
                    'body': cleaned_body
                })
                
                # 存 DB
                db.write_message(msg, is_filtered=False)
                db.write_analysis(msg['message_id'], analysis)
            
            print(f'Fetched {len(messages)} messages from {account_info["email"]}')
        
        except Exception as e:
            print(f'Fetch error for {account_info["email"]}: {e}')
    
    db.close()

# CLI 入口
if __name__ == '__main__':
    asyncio.run(fetch_and_analyze())
```

### 7.2 日报任务(app/tasks/digest.py)

```python
from datetime import date
from app.modules.digest import DailyDigest
from app.db import get_session
from app.config import settings

async def generate_and_send_digest():
    """Cron 生成并推送日报"""
    
    db = get_session()
    digest_gen = DailyDigest(db)
    
    for idx, account_info in settings.gmail_accounts.items():
        account_id = db.get_account_id(account_info['email'])
        
        # 生成日报
        result = await digest_gen.generate(account_id)
        
        # 推送(此处仅 stdout,实际可接飞书/邮件)
        print(f"\n=== Digest for {account_info['email']} ===\n")
        print(result['content'])
        
        # 存 DB
        db.write_digest(account_id, result)

if __name__ == '__main__':
    import asyncio
    asyncio.run(generate_and_send_digest())
```

### 7.3 Railway Cron 配置(docker/railway.toml)

```toml
[build]
builder = "dockerfile"
dockerfile = "./docker/Dockerfile"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
healthcheckPath = "/health"
healthcheckInterval = 10

# 环境变量(在 Railway 仪表盘手动设置,或导入 .env)
[env]
PYTHONUNBUFFERED = "1"
LOG_LEVEL = "INFO"

# 定时任务
[[crons]]
schedule = "*/5 * * * *"  # 每 5 分钟
command = "python -m app.tasks.fetch"

[[crons]]
schedule = "0 8 * * *"    # 每天 8 点
command = "python -m app.tasks.digest"

# 持久化卷(SQLite)
[[volumes]]
mount_path = "/app/data"
```

---

## 8. Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 初始化数据库
RUN python scripts/init_db.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 9. FastAPI 入口(app/main.py)

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging
from app.config import settings

app = FastAPI(title='Gmail AI Analyzer', version='0.2')
logger = logging.getLogger(__name__)

@app.get('/health')
async def health():
    """Health check endpoint for Railway"""
    return {'status': 'ok'}

@app.get('/digest/{date_str}')
async def get_digest(date_str: str):
    """
    可选:查看过往日报。
    
    GET /digest/2026-06-29
    """
    from app.db import get_session
    from app.modules.digest import DailyDigest
    
    db = get_session()
    digest_gen = DailyDigest(db)
    result = await digest_gen.generate(gmail_account_id=1, date_str=date_str)
    
    return {
        'date': date_str,
        'format': result['format'],
        'content': result['content']
    }

@app.on_event('startup')
async def startup():
    logger.info('Gmail AI Analyzer started')

@app.on_event('shutdown')
async def shutdown():
    logger.info('Gmail AI Analyzer shutdown')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
```

---

## 10. 常见问题与调试

### 10.1 Gmail API 授权失败

**问题**:`invalid_grant` 或 refresh token 过期。

**原因**:
- Testing 模式 + External:token 7 天失效。
- 改了 Google 密码(含 Gmail scope)。
- 6 个月未使用。
- 超过 100 个 token 限制。

**解决**:
- 把 OAuth app 发布为 **Production**(个人用<100、免验证)。
- 捕获 `invalid_grant`,标记该账号"需重新授权"。
- 定期在本地手动刷新一次 token:
  ```bash
  python scripts/refresh_tokens.py
  ```

### 10.2 模型 API 超时或错误

**问题**:调用模型 API 返回 500 或超时。

**解决**:
- Analyzer 已有 fallback:返回默认值,该封邮件标记为"分析失败",下轮重试。
- 加日志:模型返回的完整错误信息存库便于调试。

### 10.3 邮件重复分析

**问题**:同一封邮件被分析了多次。

**原因**:忘记更新 `last_history_id` 或数据库 `message_id` 去重不工作。

**解决**:
- 用 `message_id UNIQUE` 约束保证 DB 级去重。
- 每次成功拉取后必须更新 `last_history_id`。

### 10.4 本地测试

```bash
# 单独测试拉取
python -m app.tasks.fetch --gmail-index 1 --dry-run

# 单独测试分析
python -c "
from app.modules.analyzer import EmailAnalyzer
import asyncio
a = EmailAnalyzer()
result = asyncio.run(a.analyze({
    'from': 'test@example.com',
    'subject': 'Test',
    'body': 'This is a test email.'
}))
print(result)
"

# 看 SQLite 内容
sqlite3 gmail_ai.db "SELECT * FROM gmail_messages LIMIT 5;"
```

### 10.5 Railway 部署调试

```bash
# SSH 进容器看日志
railway shell

# 查 cron 任务运行历史
railway logs --tail 50 --follow

# 手动触发拉取任务(测试)
railway run python -m app.tasks.fetch
```

---

## 11. 部署流程

### 11.1 本地测试完成后

1. **推到 GitHub**:
   ```bash
   git add .
   git commit -m 'feat: initial Gmail AI analyzer'
   git push origin main
   ```

2. **Railway 新建项目**:
   ```bash
   npm install -g @railway/cli
   railway login
   railway init
   ```

3. **连接 GitHub**:
   - Railway 仪表盘 → New Project → GitHub repo
   - 选择 `main` 分支,自动部署

4. **设置环境变量**:
   - 仪表盘 → Variables → 粘贴 `.env` 内容
   - 或 `railway variables:set KEY=VALUE` CLI

5. **添加持久卷**(SQLite):
   - 仪表盘 → Volumes → 挂载 `/app/data` 到 persistent storage

6. **验证 Cron 任务**:
   - 仪表盘 → Crons → 看运行历史

### 11.2 首次授权流程(人工)

```bash
# 本地跑授权服务(临时)
python scripts/oauth_server.py

# 访问 http://localhost:8000/auth/gmail/1
# 浏览器跳到 Google,授权你的 Gmail 1
# 自动保存 refresh_token 到 .env

# 后续写进 Railway 环境变量
railway variables:set GMAIL_REFRESH_TOKEN_1=...
```

---

## 12. 下一步(二期 feature)

- 起草回复(模型生成)。
- 跨邮箱检索。
- 写回 Gmail 标签(`gmail.modify`)。
- 飞书卡片推送。
- 用户自定义规则。
- 附件解析(PDF 账单)。

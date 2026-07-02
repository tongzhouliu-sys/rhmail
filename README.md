# RHMail AI

**[English](#english)** | **[中文](#中文)**

---

<a id="english"></a>

## 🌐 English

A self-hosted AI-powered email analysis system that automatically syncs your Gmail accounts, uses LLMs to classify, rate, and summarize emails, and generates daily Markdown digests.

### Features

- **Multi-Gmail Account Management** — OAuth 2.0 authorization with incremental sync; add, disable, or remove accounts via the web dashboard
- **Two-Stage Cost Reduction** — Rule-based pre-filtering (allowlist/blocklist, `List-Unsubscribe` header, marketing regex) + HTML cleaning to minimize LLM API calls
- **LLM-Powered Analysis** — Calls any OpenAI-compatible endpoint to produce 6-category classification, 1–5 importance rating, one-line summary, and structured key-point digests
- **Daily Email Digests** — Automatically generates Markdown digests grouped by category and sorted by importance
- **Web Dashboard** — Modern dark-themed UI with email browsing, multi-dimensional filtering, detail views, and digest archives
- **Decoupled Task Architecture** — Web server and background jobs run as separate processes, designed for cloud cron schedulers like Railway Crons

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Web Framework | FastAPI + Uvicorn |
| Templating | Jinja2 |
| ORM | SQLAlchemy 2.0 (SQLite by default, PostgreSQL supported) |
| Email | Gmail API (`gmail.readonly`) + Google OAuth 2.0 |
| LLM | Any OpenAI-compatible endpoint (OpenAI / DeepSeek / local models) |
| HTML Cleaning | BeautifulSoup4 |
| Deployment | Docker + Railway |
| Frontend | Vanilla HTML/CSS (no JS framework) |

### Quick Start

#### Local Development

```bash
# 1. Clone the project
git clone <repo-url> && cd rhmail

# 2. Create a virtual environment
python3 -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your actual values (see Configuration below)

# 5. Start the web server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. (Optional) Run background jobs manually
python -m app.jobs fetch    # Fetch & analyze emails
python -m app.jobs digest   # Generate daily digest
```

#### Docker

```bash
docker build -t rhmail .
docker run -p 8000:8000 --env-file .env -v ./data:/app/data rhmail
```

#### Railway Deployment

The project includes a `railway.toml` configuration for one-click deployment:

- **Web Service**: Auto-starts the FastAPI application
- **Cron Jobs**: Fetches emails every 60 minutes; generates daily digest at 00:00 UTC
- **Health Check**: `GET /health`

### Configuration

All settings are managed via environment variables. See `.env.example` for reference:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | Yes |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | Yes |
| `LLM_API_BASE` | LLM API base URL (OpenAI-compatible) | Yes |
| `LLM_API_KEY` | LLM API key | Yes |
| `DASHBOARD_PASSWORD` | Web dashboard login password | Yes |
| `SECRET_KEY` | Cookie signing key (generate with `openssl rand -hex 32`) | Yes |
| `LLM_MODEL` | Model name | No, default `gpt-4o-mini` |
| `DATABASE_URL` | Database connection string | No, default SQLite |
| `OAUTH_REDIRECT_URI` | OAuth callback URL | Required for deployment |
| `BACKFILL_DAYS` | Days to backfill on first sync | No, default `2` |
| `BODY_MAX_CHARS` | Max characters of email body sent to LLM | No, default `2000` |
| `WHITELIST_FROM` | Allowlisted senders (comma-separated) | No |
| `BLACKLIST_FROM` | Blocklisted senders (comma-separated) | No |
| `TZ` | Timezone | No, default `Asia/Singapore` |

### Project Structure

```
rhmail/
├── app/                    # Core application code
│   ├── main.py            # FastAPI routes & web entry
│   ├── config.py          # Environment variable configuration
│   ├── db.py              # Database engine & auto-migration
│   ├── models.py          # ORM models (4 tables)
│   ├── auth.py            # Cookie-based authentication
│   ├── oauth.py           # Google OAuth 2.0 flow
│   ├── gmail.py           # Gmail API incremental sync
│   ├── prefilter.py       # Rule-based pre-filtering
│   ├── cleaner.py         # HTML cleaning & text extraction
│   ├── analyzer.py        # LLM analysis & JSON parsing
│   ├── digest.py          # Markdown digest generation
│   └── jobs.py            # CLI job entry point
├── templates/             # Jinja2 HTML templates
├── static/                # CSS + JS static assets
├── scripts/               # Utility scripts
├── data/                  # SQLite data storage
├── Dockerfile
├── railway.toml
└── requirements.txt
```

### Architecture Overview

```
┌──────────────────────────────────────────────┐
│              Web Dashboard                    │
│         FastAPI + Jinja2 + Auth               │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────┴───────────────────────────┐
│             Background Jobs                   │
│    Gmail Sync → Pre-filter → LLM Analysis     │
└──────────────────┬───────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
 Gmail API   LLM Endpoint   Database
 (OAuth 2.0)  (OpenAI-compat)  (SQLAlchemy)
```

### Database

4 tables with auto-migration on startup (no Alembic required):

- **`gmail_accounts`** — Gmail credentials, sync state, OAuth tokens
- **`gmail_messages`** — Email messages with headers and cleaned body text
- **`analysis_results`** — AI analysis results (category, rating, summary, key points)
- **`daily_digests`** — Daily Markdown digest content

### Design Principles

- **Single-User Self-Hosted** — No multi-tenancy, no registration system; one password protects the entire dashboard
- **Read-Only Access** — Only requests `gmail.readonly` scope; never sends or modifies emails
- **Lightweight Integration** — Direct HTTP calls to LLM endpoints; no LangChain or other heavy dependencies
- **Decoupled Deployment** — Web server and background jobs run as independent processes, compatible with cloud cron schedulers
- **Auto-Migration** — Detects and adds missing columns on startup with zero manual maintenance

### Production Recommendations

- Use **PostgreSQL** instead of SQLite to avoid multi-process write conflicts
- Set `OAUTH_REDIRECT_URI` to your actual deployment domain
- Use a strong password and a random `SECRET_KEY`
- Configure Railway Crons or external schedulers (e.g., cron / systemd timer)

---

<a id="中文"></a>

## 🇨🇳 中文

自托管的 AI 邮件分析系统 —— 自动同步 Gmail，利用 LLM 智能分类、评分、摘要，每日生成邮件简报。

### 功能特性

- **多 Gmail 账号管理** — OAuth 2.0 授权，增量同步，支持在 Web 后台添加/禁用/删除账号
- **两阶段降本** — 规则预过滤（黑白名单、List-Unsubscribe、营销正则）+ HTML 清洗，减少 LLM 调用量
- **LLM 智能分析** — 调用任意 OpenAI 兼容接口，输出 6 类分类、1-5 重要性评分、一句话摘要、结构化要点
- **每日邮件简报** — 自动生成 Markdown 格式的每日摘要，按分类分组、重要性排序
- **Web 看板** — 现代深色主题界面，支持邮件浏览、多维筛选、详情查看、摘要归档
- **解耦任务架构** — Web 服务与后台任务独立运行，适配 Railway Crons 等云定时调度

### 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI + Uvicorn |
| 模板 | Jinja2 |
| ORM | SQLAlchemy 2.0（默认 SQLite，支持 PostgreSQL） |
| 邮件 | Gmail API（`gmail.readonly`）+ Google OAuth 2.0 |
| LLM | 任意 OpenAI 兼容端点（OpenAI / DeepSeek / 本地模型） |
| HTML 清洗 | BeautifulSoup4 |
| 部署 | Docker + Railway |
| 前端 | 原生 HTML/CSS（无 JS 框架） |

### 快速开始

#### 本地开发

```bash
# 1. 克隆项目
git clone <repo-url> && cd rhmail

# 2. 创建虚拟环境
python3 -m venv venv && source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值（见下方配置说明）

# 5. 启动 Web 服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6.（可选）手动运行后台任务
python -m app.jobs fetch    # 拉取并分析邮件
python -m app.jobs digest   # 生成每日摘要
```

#### Docker

```bash
docker build -t rhmail .
docker run -p 8000:8000 --env-file .env -v ./data:/app/data rhmail
```

#### Railway 部署

项目包含 `railway.toml` 配置，支持一键部署：

- **Web 服务**：自动启动 FastAPI 应用
- **定时任务**：每 60 分钟拉取邮件，每日 00:00 UTC 生成摘要
- **健康检查**：`GET /health`

### 配置说明

所有配置通过环境变量管理，参考 `.env.example`：

| 变量 | 说明 | 必填 |
|------|------|------|
| `GOOGLE_CLIENT_ID` | Google OAuth 客户端 ID | 是 |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 客户端密钥 | 是 |
| `LLM_API_BASE` | LLM API 地址（OpenAI 兼容） | 是 |
| `LLM_API_KEY` | LLM API 密钥 | 是 |
| `DASHBOARD_PASSWORD` | Web 界面登录密码 | 是 |
| `SECRET_KEY` | Cookie 签名密钥（`openssl rand -hex 32` 生成） | 是 |
| `LLM_MODEL` | 模型名称 | 否，默认 `gpt-4o-mini` |
| `DATABASE_URL` | 数据库连接字符串 | 否，默认 SQLite |
| `OAUTH_REDIRECT_URI` | OAuth 回调地址 | 部署时必填 |
| `BACKFILL_DAYS` | 首次同步回溯天数 | 否，默认 `2` |
| `BODY_MAX_CHARS` | 邮件正文最大字符数 | 否，默认 `2000` |
| `WHITELIST_FROM` | 白名单发件人（逗号分隔） | 否 |
| `BLACKLIST_FROM` | 黑名单发件人（逗号分隔） | 否 |
| `TZ` | 时区 | 否，默认 `Asia/Singapore` |

### 项目结构

```
rhmail/
├── app/                    # 核心应用代码
│   ├── main.py            # FastAPI 路由与 Web 入口
│   ├── config.py          # 环境变量配置
│   ├── db.py              # 数据库引擎与自动迁移
│   ├── models.py          # ORM 模型（4 张表）
│   ├── auth.py            # Cookie 认证
│   ├── oauth.py           # Google OAuth 2.0 流程
│   ├── gmail.py           # Gmail API 增量同步
│   ├── prefilter.py       # 规则预过滤
│   ├── cleaner.py         # HTML 清洗与正文提取
│   ├── analyzer.py        # LLM 分析与 JSON 解析
│   ├── digest.py          # Markdown 摘要生成
│   └── jobs.py            # CLI 任务入口
├── templates/             # Jinja2 HTML 模板
├── static/                # CSS + JS 静态资源
├── scripts/               # 辅助脚本
├── data/                  # SQLite 数据存放
├── Dockerfile
├── railway.toml
└── requirements.txt
```

### 架构概览

```
┌──────────────────────────────────────────────┐
│              Web Dashboard                    │
│         FastAPI + Jinja2 + Auth               │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────┴───────────────────────────┐
│             Background Jobs                   │
│    Gmail Sync → Pre-filter → LLM Analysis     │
└──────────────────┬───────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
 Gmail API   LLM Endpoint   Database
 (OAuth 2.0)  (OpenAI 兼容)  (SQLAlchemy)
```

### 数据库

4 张表，启动时自动迁移（无需 Alembic）：

- **`gmail_accounts`** — Gmail 账号凭证、同步状态、OAuth Token
- **`gmail_messages`** — 邮件消息（含信头、清洗后正文）
- **`analysis_results`** — AI 分析结果（分类、评分、摘要、要点）
- **`daily_digests`** — 每日 Markdown 摘要

### 设计原则

- **单用户自托管** — 无多租户，无注册系统，一个密码保护全站
- **只读访问** — 仅请求 `gmail.readonly` 权限，不发送/修改邮件
- **轻量集成** — 直接 HTTP 调用 LLM，无 LangChain 等重型依赖
- **解耦部署** — Web 服务与后台任务独立进程，适配云 Cron 调度
- **自动迁移** — 启动时检测并添加缺失字段，零手动维护

### 生产部署建议

- 使用 **PostgreSQL** 替代 SQLite，避免多进程写入冲突
- 设置 `OAUTH_REDIRECT_URI` 为实际部署域名
- 使用强密码和随机 `SECRET_KEY`
- 配置 Railway Crons 或外部定时任务（如 cron / systemd timer）

---

## License

MIT

---

© 2026 RHCLOUD PTE LTD. All rights reserved.

Developer: TONGZHOU LIU

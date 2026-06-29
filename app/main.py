import logging
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import GmailAccount, GmailMessage, AnalysisResult, DailyDigest
from app.auth import make_cookie, require_page, require_api, COOKIE_NAME, _valid
from app.jobs import fetch_and_analyze, run_daily_digest
from app import oauth

from app.cleaner import clean_text, render_markdown, render_summary

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

app = FastAPI(title="Gmail AI Analyzer", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["clean_text"] = clean_text
templates.env.filters["markdown"] = render_markdown
templates.env.filters["render_summary"] = render_summary

CATEGORY_MAP = {
    "urgent": "紧急·需回复",
    "finance": "金融·账户告警",
    "legal": "法律·合同",
    "notice": "重要通知",
    "marketing": "订阅·营销",
    "social": "社交其他",
}
REV_CATEGORY_MAP = {v: k for k, v in CATEGORY_MAP.items()}
CATEGORIES_LIST = [{"slug": s, "name": n} for s, n in CATEGORY_MAP.items()]


def resolve_category_name(cat_input: str) -> str:
    if not cat_input:
        return ""
    return CATEGORY_MAP.get(cat_input, cat_input)


def get_category_slug(cat_name: str) -> str:
    return REV_CATEGORY_MAP.get(cat_name, cat_name)


templates.env.filters["cat_slug"] = get_category_slug


_sidebar_cache: dict = {"data": None, "ts": 0.0}
_SIDEBAR_TTL = 300  # 5 minutes


def get_sidebar_context(db):
    now = time.monotonic()
    if _sidebar_cache["data"] is not None and now - _sidebar_cache["ts"] < _SIDEBAR_TTL:
        return _sidebar_cache["data"]
    by_cat = dict(
        db.execute(
            select(AnalysisResult.category, func.count()).group_by(AnalysisResult.category)
        ).all()
    )
    important_count = db.scalar(
        select(func.count(AnalysisResult.id)).where(AnalysisResult.importance >= 4)
    ) or 0
    result = {
        "categories": CATEGORIES_LIST,
        "by_cat": by_cat,
        "important_count": important_count,
    }
    _sidebar_cache["data"] = result
    _sidebar_cache["ts"] = now
    return result


scheduler = AsyncIOScheduler(timezone=settings.timezone)


@app.on_event("startup")
async def _startup():
    init_db()
    scheduler.add_job(
        fetch_and_analyze,
        "interval",
        minutes=settings.fetch_interval_minutes,
        id="fetch_emails_job",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_digest,
        "cron",
        hour=settings.digest_hour,
        minute=0,
        id="daily_digest_job",
        replace_existing=True,
    )
    scheduler.start()
    log.info("⏰ APScheduler 内置定时任务已启动：每 %d 分钟同步邮件，每天 %d:00 生成日报", settings.fetch_interval_minutes, settings.digest_hour)


@app.on_event("shutdown")
async def _shutdown():
    scheduler.shutdown()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.png")



# ---------- 认证 ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(password: str = Form(...)):
    if password != settings.dashboard_password:
        return JSONResponse({"detail": "密码错误"}, status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        make_cookie(),
        max_age=settings.session_lifetime_days * 86400,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return resp


@app.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------- 看板页面 ----------
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def dashboard(request: Request):
    db = SessionLocal()
    try:
        digests = db.scalars(
            select(DailyDigest).order_by(DailyDigest.date.desc()).limit(14)
        ).all()
        ctx = {"request": request, "digests": digests}
        ctx.update(get_sidebar_context(db))
        ctx["total"] = sum(ctx["by_cat"].values())
        ctx["important"] = ctx["important_count"]
        return templates.TemplateResponse("dashboard.html", ctx)
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
        cat_name = resolve_category_name(category)
        cat_slug = get_category_slug(cat_name) if cat_name else ""

        q = (
            select(GmailMessage, AnalysisResult)
            .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
        )
        if cat_name:
            q = q.where(AnalysisResult.category == cat_name)
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
        ctx = {
            "request": request,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, -(-total // limit)),
            "f": {
                "category": cat_slug,
                "category_name": cat_name,
                "importance": importance,
                "date_from": date_from,
                "date_to": date_to,
            },
        }
        ctx.update(get_sidebar_context(db))
        return templates.TemplateResponse("emails.html", ctx)
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
        ctx = {
            "request": request,
            "m": m,
            "a": a,
        }
        ctx.update(get_sidebar_context(db))
        return templates.TemplateResponse("email_detail.html", ctx)
    finally:
        db.close()


@app.get("/digests", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digests_page(request: Request):
    db = SessionLocal()
    try:
        items = db.scalars(
            select(DailyDigest).order_by(DailyDigest.date.desc()).limit(90)
        ).all()
        ctx = {"request": request, "items": items}
        ctx.update(get_sidebar_context(db))
        return templates.TemplateResponse("digests.html", ctx)
    finally:
        db.close()


@app.get("/digests/{day}", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digest_detail(request: Request, day: str):
    db = SessionLocal()
    try:
        items = db.scalars(
            select(DailyDigest).where(DailyDigest.date == day)
        ).all()
        ctx = {
            "request": request,
            "day": day,
            "items": items,
        }
        ctx.update(get_sidebar_context(db))
        return templates.TemplateResponse("digest_detail.html", ctx)
    finally:
        db.close()


# ---------- JSON API ----------
@app.get("/api/emails", dependencies=[Depends(require_api)])
async def api_emails(
    limit: int = 20,
    offset: int = 0,
    category: str = "",
    importance: int = 0,
):
    db = SessionLocal()
    try:
        cat_name = resolve_category_name(category)
        q = (
            select(GmailMessage, AnalysisResult)
            .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
        )
        if cat_name:
            q = q.where(AnalysisResult.category == cat_name)
        if importance:
            q = q.where(AnalysisResult.importance == importance)
        rows = db.execute(
            q.order_by(GmailMessage.received_at.desc()).limit(limit).offset(offset)
        ).all()
        return {"items": [
            {
                "id": m.id,
                "from": m.from_email,
                "subject": m.subject,
                "received_at": m.received_at.isoformat() if m.received_at else None,
                "category": a.category,
                "importance": a.importance,
                "one_line": a.one_line,
            }
            for m, a in rows
        ]}
    finally:
        db.close()


@app.get("/accounts", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def accounts_page(request: Request, msg: str = Query("")):
    db = SessionLocal()
    try:
        accounts = db.scalars(
            select(GmailAccount).order_by(GmailAccount.created_at.desc())
        ).all()
        ctx = {
            "request": request,
            "accounts": accounts,
            "msg": msg,
        }
        ctx.update(get_sidebar_context(db))
        return templates.TemplateResponse("accounts.html", ctx)
    except Exception:
        # Never let a DB/render error turn the whole page into a raw 500.
        log.exception("Failed to render accounts page")
        ctx = {
            "request": request,
            "accounts": [],
            "msg": msg or "加载邮箱列表时出错，请稍后重试或查看服务端日志。",
            "categories": CATEGORIES_LIST,
            "by_cat": {},
            "important_count": 0,
        }
        return templates.TemplateResponse("accounts.html", ctx, status_code=200)
    finally:
        db.close()


def get_redirect_uri(request: Request) -> str:
    if settings.oauth_redirect_uri:
        return settings.oauth_redirect_uri.strip()
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{scheme}://{request.url.netloc}/oauth/callback"


@app.get("/accounts/add")
@app.get("/auth/google")
async def accounts_add(request: Request):
    """Initiate the Google OAuth flow to add a Gmail account and auto-authenticate dashboard session."""
    if not settings.google_client_id or not settings.google_client_secret:
        return RedirectResponse("/accounts?msg=错误：未配置 GOOGLE_CLIENT_ID 或 GOOGLE_CLIENT_SECRET 环境变量", status_code=302)
    state = oauth.generate_state()
    redirect_uri = get_redirect_uri(request)
    auth_url = oauth.get_auth_url(state, redirect_uri=redirect_uri)
    resp = RedirectResponse(auth_url, status_code=302)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return resp


@app.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
):
    """Handle the Google OAuth callback, update database and issue dashboard session cookie for auto-login."""
    if error:
        log.warning("OAuth callback error: %s", error)
        return RedirectResponse(f"/accounts?msg=授权失败: {error}", status_code=302)

    # Verify CSRF state
    saved_state = request.cookies.get("oauth_state", "")
    if not state or state != saved_state:
        return RedirectResponse("/accounts?msg=授权验证失败(state 不匹配)", status_code=302)

    try:
        redirect_uri = get_redirect_uri(request)
        result = await oauth.exchange_code(code, redirect_uri=redirect_uri)
    except ValueError as e:
        log.exception("OAuth exchange failed: %s", e)
        return RedirectResponse(f"/accounts?msg=授权交换失败: {e}", status_code=302)

    # Save or update the account in the database
    db = SessionLocal()
    try:
        existing = db.scalar(
            select(GmailAccount).where(GmailAccount.email == result["email"])
        )
        if existing:
            existing.refresh_token = result["refresh_token"]
            existing.needs_reauth = False
            existing.is_active = True
            existing.added_via = "oauth"
            msg = f"已成功通过 Google 授权登录，更新邮箱 {result['email']}"
        else:
            db.add(GmailAccount(
                email=result["email"],
                refresh_token=result["refresh_token"],
                added_via="oauth",
            ))
            msg = f"已成功添加并授权邮箱 {result['email']}"
        db.commit()
    except Exception:
        # Authorization with Google succeeded but persisting the account failed;
        # surface a friendly message instead of a raw 500.
        db.rollback()
        log.exception("Failed to save OAuth account for %s", result.get("email"))
        return RedirectResponse("/accounts?msg=保存账号失败，请重试或查看服务端日志。", status_code=302)
    finally:
        db.close()

    resp = RedirectResponse(f"/accounts?msg={msg}", status_code=302)
    # Auto-login to dashboard session upon successful Google OAuth
    resp.set_cookie(
        COOKIE_NAME,
        make_cookie(),
        max_age=settings.session_lifetime_days * 86400,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    resp.delete_cookie("oauth_state")
    return resp


@app.post("/api/accounts/{account_id}/toggle", dependencies=[Depends(require_api)])
async def toggle_account(account_id: int):
    """Toggle the is_active state of a Gmail account."""
    db = SessionLocal()
    try:
        acc = db.get(GmailAccount, account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
        acc.is_active = not acc.is_active
        db.commit()
        return {"id": acc.id, "is_active": acc.is_active}
    finally:
        db.close()


@app.get("/api/accounts/{account_id}/reauth", dependencies=[Depends(require_page)])
async def reauth_account(account_id: int, request: Request):
    """Re-initiate OAuth for an account that needs re-authorization."""
    db = SessionLocal()
    try:
        acc = db.get(GmailAccount, account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
    finally:
        db.close()
    # Redirect into the standard OAuth flow
    state = oauth.generate_state()
    redirect_uri = get_redirect_uri(request)
    auth_url = oauth.get_auth_url(state, redirect_uri=redirect_uri)
    resp = RedirectResponse(auth_url, status_code=302)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return resp


@app.delete("/api/accounts/{account_id}", dependencies=[Depends(require_api)])
async def delete_account(account_id: int):
    """Delete a Gmail account and all its associated messages and analysis results."""
    db = SessionLocal()
    try:
        acc = db.get(GmailAccount, account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
        # Delete associated analysis results, messages, digests
        messages = db.scalars(
            select(GmailMessage).where(GmailMessage.account_id == account_id)
        ).all()
        for msg in messages:
            analysis = db.scalar(
                select(AnalysisResult).where(AnalysisResult.message_pk == msg.id)
            )
            if analysis:
                db.delete(analysis)
        for msg in messages:
            db.delete(msg)
        digests = db.scalars(
            select(DailyDigest).where(DailyDigest.account_id == account_id)
        ).all()
        for d in digests:
            db.delete(d)
        db.delete(acc)
        db.commit()
        return {"ok": True, "deleted_email": acc.email}
    finally:
        db.close()

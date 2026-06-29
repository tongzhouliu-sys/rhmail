import logging
from fastapi import FastAPI, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import GmailMessage, AnalysisResult, DailyDigest
from app.auth import make_cookie, require_page, require_api, COOKIE_NAME, _valid

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Gmail AI Analyzer", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CATEGORIES = ["紧急·需回复", "金融·账户告警", "法律·合同", "重要通知", "订阅·营销", "社交其他"]


@app.on_event("startup")
async def _startup():
    init_db()


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
        total = db.scalar(select(func.count(AnalysisResult.id))) or 0
        important = db.scalar(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.importance >= 4)
        ) or 0
        by_cat = dict(
            db.execute(
                select(AnalysisResult.category, func.count()).group_by(AnalysisResult.category)
            ).all()
        )
        digests = db.scalars(
            select(DailyDigest).order_by(DailyDigest.date.desc()).limit(14)
        ).all()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "total": total,
            "important": important,
            "by_cat": by_cat,
            "categories": CATEGORIES,
            "digests": digests,
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
        q = (
            select(GmailMessage, AnalysisResult)
            .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
        )
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
            "request": request,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, -(-total // limit)),
            "categories": CATEGORIES,
            "f": {
                "category": category,
                "importance": importance,
                "date_from": date_from,
                "date_to": date_to,
            },
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
        return templates.TemplateResponse("email_detail.html", {"request": request, "m": m, "a": a})
    finally:
        db.close()


@app.get("/digests", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digests_page(request: Request):
    db = SessionLocal()
    try:
        items = db.scalars(
            select(DailyDigest).order_by(DailyDigest.date.desc()).limit(90)
        ).all()
        return templates.TemplateResponse("digests.html", {"request": request, "items": items})
    finally:
        db.close()


@app.get("/digests/{day}", response_class=HTMLResponse, dependencies=[Depends(require_page)])
async def digest_detail(request: Request, day: str):
    db = SessionLocal()
    try:
        items = db.scalars(
            select(DailyDigest).where(DailyDigest.date == day)
        ).all()
        return templates.TemplateResponse("digest_detail.html", {
            "request": request,
            "day": day,
            "items": items,
        })
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
        q = (
            select(GmailMessage, AnalysisResult)
            .join(AnalysisResult, AnalysisResult.message_pk == GmailMessage.id)
        )
        if category:
            q = q.where(AnalysisResult.category == category)
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

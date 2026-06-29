import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import GmailAccount, GmailMessage, AnalysisResult, DailyDigest
from app.config import settings
from app import gmail, prefilter, cleaner, analyzer, digest
from google.auth.exceptions import RefreshError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jobs")


def _sync_accounts_from_config(db) -> None:
    for acc in settings.gmail_accounts:
        row = db.scalar(select(GmailAccount).where(GmailAccount.email == acc["email"]))
        if row:
            row.refresh_token = acc["refresh_token"]
            row.needs_reauth = False
        else:
            db.add(GmailAccount(email=acc["email"], refresh_token=acc["refresh_token"]))
    db.commit()


async def fetch_and_analyze() -> None:  # noqa: C901
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
                acc.needs_reauth = True
                db.commit()
                log.warning("account %s needs reauth", acc.email)
                continue
            except Exception as e:
                log.exception("fetch failed for %s: %s", acc.email, e)
                continue

            for msg in messages:
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
                    account_id=acc.id,
                    message_id=msg["message_id"],
                    from_email=msg["from_email"],
                    from_name=msg["from_name"],
                    subject=msg["subject"],
                    received_at=msg["received_at"],
                    is_filtered=filtered,
                    body_text=cleaner.clean_body(msg["body_text"], msg["body_html"]),
                )
                db.add(row)
                db.flush()

                if not filtered:
                    res = await analyzer.analyze({
                        "from_email": msg["from_email"],
                        "subject": msg["subject"],
                        "body_text": row.body_text,
                    })
                    db.add(AnalysisResult(
                        message_pk=row.id,
                        category=res["category"],
                        importance=res["importance"],
                        one_line=res["one_line"],
                        summary=res["summary"],
                        model_used=res["model_used"],
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
                .where(
                    GmailMessage.account_id == acc.id,
                    GmailMessage.received_at >= start,
                    GmailMessage.received_at < end,
                )
            ).all()
            md, total, important = digest.render_markdown(day, rows)
            existing = db.scalar(
                select(DailyDigest).where(
                    DailyDigest.date == day,
                    DailyDigest.account_id == acc.id,
                )
            )
            if existing:
                existing.content_md = md
                existing.total_emails = total
                existing.important_emails = important
            else:
                db.add(DailyDigest(
                    date=day,
                    account_id=acc.id,
                    content_md=md,
                    total_emails=total,
                    important_emails=important,
                ))
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    init_db()
    if cmd == "fetch":
        log.info("🚀 启动邮件同步与分析任务 (fetch)...")
        asyncio.run(fetch_and_analyze())
        log.info("✅ 邮件同步与分析任务完成并退出。")
    elif cmd == "digest":
        log.info("🚀 启动每日生成日报任务 (digest)...")
        asyncio.run(run_daily_digest())
        log.info("✅ 每日生成日报任务完成并退出。")
    elif cmd in ("all", "sync"):
        log.info("🚀 启动全量任务 (fetch + digest)...")
        asyncio.run(fetch_and_analyze())
        asyncio.run(run_daily_digest())
        log.info("✅ 全量任务完成并退出。")
    else:
        print("Usage: python -m app.jobs [fetch|digest|all|sync]", file=sys.stderr)
        sys.exit(1)


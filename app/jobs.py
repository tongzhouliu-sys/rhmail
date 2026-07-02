import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone as tz
from sqlalchemy import select, func

from app.db import SessionLocal, init_db
from app.models import GmailAccount, GmailMessage, AnalysisResult, DailyDigest
from app.config import settings
from app import gmail, prefilter, cleaner, analyzer, digest
from google.auth.exceptions import RefreshError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jobs")


def _sync_accounts_from_config(db) -> None:
    """Seed accounts from environment variables (first-time import only)."""
    for acc in settings.gmail_accounts:
        row = db.scalar(select(GmailAccount).where(GmailAccount.email == acc["email"]))
        if row:
            # Only update token if account was originally added via env vars
            if row.added_via == "env":
                row.refresh_token = acc["refresh_token"]
                row.needs_reauth = False
        else:
            db.add(GmailAccount(
                email=acc["email"],
                refresh_token=acc["refresh_token"],
                added_via="env",
            ))
    db.commit()


async def fetch_and_analyze() -> None:  # noqa: C901
    db = SessionLocal()
    _sem = asyncio.Semaphore(5)

    async def _analyze_one(row_id: int, msg_data: dict):
        async with _sem:
            return row_id, await analyzer.analyze(msg_data)

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

            # Phase 1: save all messages, collect those needing analysis
            to_analyze: list[tuple[int, dict]] = []
            for msg in messages:
                row = db.scalar(
                    select(GmailMessage).where(
                        GmailMessage.account_id == acc.id,
                        GmailMessage.message_id == msg["message_id"],
                    )
                )
                filtered = prefilter.should_filter_out(msg)
                if not row:
                    row = GmailMessage(
                        account_id=acc.id,
                        message_id=msg["message_id"],
                        from_email=msg["from_email"],
                        from_name=msg["from_name"],
                        to_email=msg.get("to_email", ""),
                        to_name=msg.get("to_name", ""),
                        subject=msg["subject"],
                        received_at=msg["received_at"],
                        is_filtered=filtered,
                        body_text=cleaner.clean_body(msg["body_text"], msg["body_html"]),
                    )
                    db.add(row)
                    db.flush()
                else:
                    row.is_filtered = filtered

                has_analysis = db.scalar(select(AnalysisResult.id).where(AnalysisResult.message_pk == row.id))
                if not filtered and not has_analysis:
                    to_analyze.append((row.id, {
                        "from_email": row.from_email,
                        "subject": row.subject,
                        "body_text": row.body_text,
                    }))

            db.commit()

            # Phase 2: concurrent LLM analysis
            if to_analyze:
                raw = await asyncio.gather(
                    *[_analyze_one(rid, d) for rid, d in to_analyze],
                    return_exceptions=True,
                )
                for item in raw:
                    if isinstance(item, Exception):
                        log.exception("LLM analysis failed: %s", item)
                        continue
                    row_id, res = item
                    db.add(AnalysisResult(
                        message_pk=row_id,
                        category=res["category"],
                        importance=res["importance"],
                        one_line=res["one_line"],
                        summary=res["summary"],
                        model_used=res["model_used"],
                    ))
                db.commit()

            acc.last_history_id = new_hid
            acc.last_sync_at = datetime.now(tz.utc).replace(tzinfo=None)
            db.commit()
            log.info("synced %s: %d new, %d analyzed", acc.email, len(messages), len(to_analyze))
    finally:
        db.close()


async def reanalyze_unanalyzed_messages() -> None:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(GmailMessage).where(
                ~select(AnalysisResult.id).where(AnalysisResult.message_pk == GmailMessage.id).exists()
            )
        ).all()
        log.info("未分析邮件共计 %d 封，开始重新触发分析...", len(rows))
        count = 0
        for row in rows:
            filtered = prefilter.should_filter_out({
                "from_email": row.from_email,
                "subject": row.subject,
            })
            row.is_filtered = filtered
            if not filtered:
                res = await analyzer.analyze({
                    "from_email": row.from_email,
                    "subject": row.subject,
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
                count += 1
            db.commit()
        log.info("✅ 补全分析完成，共成功分析 %d 封邮件。", count)
    finally:
        db.close()


async def reanalyze_all_messages() -> None:
    """Full refresh: re-run AI analysis on EVERY non-filtered message and
    overwrite its existing AnalysisResult, regenerating summaries in the new
    structured-block format. Per-message error isolation + progress logging.
    Processes in batches of 100 to avoid loading the full table into memory."""
    db = SessionLocal()
    try:
        total = db.scalar(select(func.count(GmailMessage.id))) or 0
        log.info("🔁 全量重刷：库内共 %d 封邮件，开始逐封重新分析...", total)
        done = analyzed = failed = 0
        batch_size = 100
        offset = 0

        while True:
            rows = db.scalars(
                select(GmailMessage).order_by(GmailMessage.id).limit(batch_size).offset(offset)
            ).all()
            if not rows:
                break

            for row in rows:
                done += 1
                try:
                    filtered = prefilter.should_filter_out({
                        "from_email": row.from_email,
                        "subject": row.subject,
                    })
                    row.is_filtered = filtered
                    if not filtered:
                        res = await analyzer.analyze({
                            "from_email": row.from_email,
                            "subject": row.subject,
                            "body_text": row.body_text,
                        })
                        # Safety: if the LLM call failed, do NOT overwrite a good
                        # existing summary with the failure placeholder.
                        if str(res.get("summary", "")).startswith("(分析失败"):
                            failed += 1
                            log.warning("分析失败，保留原摘要 message_pk=%s", row.id)
                            db.commit()
                            if done % 20 == 0 or done == total:
                                log.info("  进度 %d/%d（已分析 %d，失败 %d）", done, total, analyzed, failed)
                            continue
                        existing = db.scalar(
                            select(AnalysisResult).where(AnalysisResult.message_pk == row.id)
                        )
                        if existing:
                            existing.category = res["category"]
                            existing.importance = res["importance"]
                            existing.one_line = res["one_line"]
                            existing.summary = res["summary"]
                            existing.model_used = res["model_used"]
                        else:
                            db.add(AnalysisResult(
                                message_pk=row.id,
                                category=res["category"],
                                importance=res["importance"],
                                one_line=res["one_line"],
                                summary=res["summary"],
                                model_used=res["model_used"],
                            ))
                        analyzed += 1
                    db.commit()
                except Exception as e:
                    db.rollback()
                    failed += 1
                    log.exception("重刷失败 message_pk=%s: %s", row.id, e)
                if done % 20 == 0 or done == total:
                    log.info("  进度 %d/%d（已分析 %d，失败 %d）", done, total, analyzed, failed)

            offset += batch_size

        log.info("✅ 全量重刷完成：共 %d 封，重新分析 %d 封，跳过(过滤) %d 封，失败 %d 封。",
                 total, analyzed, total - analyzed - failed, failed)
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
    elif cmd == "reanalyze":
        log.info("🚀 启动数据库存量邮件补全分析任务 (reanalyze)...")
        asyncio.run(reanalyze_unanalyzed_messages())
        log.info("✅ 存量邮件补全分析完成。")
    elif cmd in ("reanalyze-all", "refresh"):
        log.info("🚀 启动全量重刷任务 (reanalyze-all)...")
        asyncio.run(reanalyze_all_messages())
        log.info("✅ 全量重刷完成。")
    elif cmd in ("all", "sync"):
        log.info("🚀 启动全量任务 (fetch + digest)...")
        asyncio.run(fetch_and_analyze())
        asyncio.run(reanalyze_unanalyzed_messages())
        asyncio.run(run_daily_digest())
        log.info("✅ 全量任务完成并退出。")
    else:
        print("Usage: python -m app.jobs [fetch|digest|reanalyze|reanalyze-all|all|sync]", file=sys.stderr)
        sys.exit(1)


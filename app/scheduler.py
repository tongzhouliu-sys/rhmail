from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.jobs import fetch_and_analyze, run_daily_digest

scheduler = AsyncIOScheduler(timezone=settings.timezone)


def start_scheduler() -> None:
    scheduler.add_job(
        fetch_and_analyze,
        "interval",
        minutes=settings.fetch_interval_minutes,
        id="fetch",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_daily_digest,
        "cron",
        hour=settings.digest_hour,
        minute=0,
        id="digest",
    )
    scheduler.start()

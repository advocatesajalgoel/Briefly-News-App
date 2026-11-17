"""APScheduler wiring for the automated pipeline.

Enabled with ``BRIEFLY_SCHEDULER_ENABLED=true``. In a multi-process deployment
run exactly one instance with the scheduler on (or move these jobs to a proper
worker) so an episode is not generated twice.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.jobs.tasks import job_daily_podcast, job_refresh_news

log = logging.getLogger("briefly.scheduler")
_scheduler: BackgroundScheduler | None = None


def _cron(expression: str, timezone: str) -> CronTrigger:
    minute, hour, day, month, day_of_week = expression.split()
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
        timezone=timezone,
    )


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("scheduler disabled (BRIEFLY_SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        job_refresh_news,
        _cron(settings.ingest_cron, settings.scheduler_timezone),
        id="refresh_news",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        job_daily_podcast,
        _cron(settings.daily_podcast_cron, settings.scheduler_timezone),
        id="daily_podcast",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info(
        "scheduler started: news '%s', daily podcast '%s' (%s)",
        settings.ingest_cron, settings.daily_podcast_cron, settings.scheduler_timezone,
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None

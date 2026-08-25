"""Production scheduler for AI Intelligence Radar.

Runs the daily radar pipeline automatically.
"""

import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app.pipeline import run_daily_radar
from app.core.logger import get_logger

logger = get_logger("scheduler")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

RUN_HOUR = int(os.getenv("RADAR_RUN_HOUR", "8"))
RUN_MINUTE = int(os.getenv("RADAR_RUN_MINUTE", "0"))

_job_lock = threading.Lock()


def daily_radar_job():
    """Execute radar pipeline with duplicate-run protection."""
    if not _job_lock.acquire(blocking=False):
        logger.warning("daily radar job skipped: previous execution still running")
        return

    try:
        logger.info("daily radar job started")
        result = run_daily_radar() or {}
        logger.info(
            "daily radar job finished, items=%s",
            len(result.get("items", [])) if isinstance(result, dict) else 0,
        )
    except Exception:
        logger.exception("daily radar job failed")
    finally:
        _job_lock.release()


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        daily_radar_job,
        "cron",
        hour=RUN_HOUR,
        minute=RUN_MINUTE,
        id="daily_radar",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        "scheduler started at %02d:%02d daily",
        RUN_HOUR,
        RUN_MINUTE,
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()

"""Production scheduler for AI Intelligence Radar.

Runs the daily radar pipeline automatically.
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler

from app.pipeline import run_daily_radar
from app.core.logger import get_logger

logger = get_logger("scheduler")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

RUN_HOUR = int(os.getenv("RADAR_RUN_HOUR", "8"))
RUN_MINUTE = int(os.getenv("RADAR_RUN_MINUTE", "0"))


def daily_radar_job():
    try:
        logger.info("daily radar job started")
        result = run_daily_radar()
        logger.info(
            "daily radar job finished, items=%s",
            len(result.get("items", [])),
        )
    except Exception:
        logger.exception("daily radar job failed")


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

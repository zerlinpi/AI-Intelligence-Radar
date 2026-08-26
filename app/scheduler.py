"""生产环境定时调度器。

每天自动执行 AI 情报日报流程。
"""

import os
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import REPORT_TIMEZONE
from app.core.logger import get_logger
from app.core.preflight import run_preflight
from app.pipeline import run_daily_radar


logger = get_logger("调度器")


def _read_schedule_value(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))

    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("配置无效：%s=%r，已使用默认值=%s", name, raw, default)
        return default

    if value < minimum or value > maximum:
        logger.warning("配置超出范围：%s=%s，已使用默认值=%s", name, value, default)
        return default

    return value


def _scheduler_timezone() -> str:
    try:
        ZoneInfo(REPORT_TIMEZONE)
        return REPORT_TIMEZONE
    except ZoneInfoNotFoundError:
        logger.error("日报时区无效：%s，调度器已回退 Asia/Shanghai", REPORT_TIMEZONE)
        return "Asia/Shanghai"


scheduler = BackgroundScheduler(timezone=_scheduler_timezone())

RUN_HOUR = _read_schedule_value("RADAR_RUN_HOUR", 8, 0, 23)
RUN_MINUTE = _read_schedule_value("RADAR_RUN_MINUTE", 0, 0, 59)

_job_lock = threading.Lock()


def daily_radar_job():
    """执行日报并避免同一进程内重复运行。"""
    if not _job_lock.acquire(blocking=False):
        logger.warning("定时日报已跳过：上一轮任务仍在运行")
        return

    try:
        preflight = run_preflight()
        if not preflight.ok:
            logger.error(
                "定时日报预检失败，已停止本轮执行：失败项=%s",
                "、".join(preflight.failures),
            )
            return

        logger.info("定时日报开始执行")
        result = run_daily_radar() or {}
        logger.info(
            "定时日报执行结束：项目数量=%s 状态=%s",
            len(result.get("items", [])) if isinstance(result, dict) else 0,
            result.get("status", "完成") if isinstance(result, dict) else "未知",
        )
    except Exception:
        logger.exception("定时日报执行失败")
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
        "调度器已启动：每天 %02d:%02d 执行 时区=%s",
        RUN_HOUR,
        RUN_MINUTE,
        _scheduler_timezone(),
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已停止")

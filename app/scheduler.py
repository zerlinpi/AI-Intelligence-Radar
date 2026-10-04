"""生产环境定时调度器。

常驻服务是北京时间 08:00 的主发布时钟：
- 07:35 预生成当天确定性本地兜底；
- 08:00 优先发送 ChatGPT Feed，Feed/GitHub 读取异常时发送本地兜底；
- GitHub Actions 仅作为延迟约 2 分钟的灾备发布器。
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import REPORT_TIMEZONE
from app.core.logger import get_logger
from app.core.run_history import record_run_safe
from scripts.prepare_local_fallback import prepare as prepare_local_fallback
from scripts.send_chatgpt_feed import main as publish_daily_feed


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

PREP_HOUR = _read_schedule_value("RADAR_FALLBACK_PREP_HOUR", 7, 0, 23)
PREP_MINUTE = _read_schedule_value("RADAR_FALLBACK_PREP_MINUTE", 35, 0, 59)
RUN_HOUR = _read_schedule_value("RADAR_RUN_HOUR", 8, 0, 23)
RUN_MINUTE = _read_schedule_value("RADAR_RUN_MINUTE", 0, 0, 59)

_prep_lock = threading.Lock()
_publish_lock = threading.Lock()


def _record_scheduler_publish(exit_code: int) -> None:
    status_path = Path("data/chatgpt-feed-status.json")
    status = {}
    if status_path.exists():
        try:
            parsed = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                status = parsed
        except (OSError, json.JSONDecodeError):
            status = {}

    record_run_safe(
        {
            "execution_id": f"scheduler-publish-{status.get('date') or 'unknown'}",
            "time": datetime.now(timezone.utc).isoformat(),
            "status": "success" if exit_code == 0 else "failed",
            "items": [],
            "policies": [],
            "feishu_cards": int(status.get("cards") or 0),
            "feishu_sent": bool(status.get("sent", False)),
            "reason": str(status.get("deduplicated_by") or status.get("source") or ""),
            "errors": [] if exit_code == 0 else [str(status.get("error") or f"exit={exit_code}")],
        }
    )


def prepare_fallback_job():
    """07:35 无条件生成当天本地兜底，避免 08:00 依赖 GitHub/ChatGPT 可用性。"""
    if not _prep_lock.acquire(blocking=False):
        logger.warning("本地兜底准备已跳过：上一轮准备仍在运行")
        return

    try:
        logger.info("07:35 本地兜底准备开始")
        result = prepare_local_fallback() or {}
        logger.info(
            "07:35 本地兜底准备结束：状态=%s 卡片=%s",
            result.get("status", "unknown") if isinstance(result, dict) else "unknown",
            result.get("cards", 0) if isinstance(result, dict) else 0,
        )
    except Exception:
        logger.exception("07:35 本地兜底准备失败")
    finally:
        _prep_lock.release()


def publish_radar_job():
    """08:00 主发布入口；严格受北京时间发送窗口保护。"""
    if not _publish_lock.acquire(blocking=False):
        logger.warning("08:00 日报发布已跳过：上一轮发布仍在运行")
        return

    try:
        os.environ.setdefault("RADAR_ENFORCE_SEND_WINDOW", "1")
        os.environ.setdefault("RADAR_SEND_WINDOW_START", "08:00")
        os.environ.setdefault("RADAR_SEND_WINDOW_END", "08:10")

        logger.info("08:00 日报主发布开始")
        exit_code = int(publish_daily_feed() or 0)
        _record_scheduler_publish(exit_code)
        if exit_code == 0:
            logger.info("08:00 日报主发布完成")
        else:
            logger.error("08:00 日报主发布失败：exit=%s；等待 GitHub Actions 灾备", exit_code)
    except Exception:
        logger.exception("08:00 日报主发布异常；等待 GitHub Actions 灾备")
    finally:
        _publish_lock.release()


# 向后兼容旧调用名称；语义已改为 08:00 发布器，而不是直接运行完整 DeepSeek pipeline。
daily_radar_job = publish_radar_job


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        prepare_fallback_job,
        "cron",
        hour=PREP_HOUR,
        minute=PREP_MINUTE,
        id="prepare_local_fallback",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=20 * 60,
    )
    scheduler.add_job(
        publish_radar_job,
        "cron",
        hour=RUN_HOUR,
        minute=RUN_MINUTE,
        id="publish_daily_radar",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        # 即使线程短暂阻塞，最多只允许 10 分钟内执行；脚本本身还有第二层窗口保护。
        misfire_grace_time=10 * 60,
    )

    scheduler.start()
    logger.info(
        "调度器已启动：%02d:%02d 预生成兜底，%02d:%02d 发布日报，时区=%s",
        PREP_HOUR,
        PREP_MINUTE,
        RUN_HOUR,
        RUN_MINUTE,
        _scheduler_timezone(),
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已停止")

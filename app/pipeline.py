from datetime import datetime, timezone
import time
import uuid

from app.cleaner import normalize_items
from app.scoring import age_hours, calculate_score
from app.ai.analyzer import analyze_item
from app.feishu import send_feishu
from app.core.logger import get_logger
from app.core.run_lock import execution_lock
from app.models.radar_item import RadarItem

from app.sources.github import GithubCollector
from app.sources.hackernews import HackerNewsCollector
from app.sources.huggingface import HuggingFaceCollector
from app.sources.arxiv import ArxivCollector
from app.sources.producthunt import ProductHuntCollector

from app.database.session import SessionLocal, init_database
from app.storage.repository import save_batch, exists


logger = get_logger("pipeline")

MAX_REPORT_ITEMS = 10
MAX_PROJECT_AGE_DAYS = 14

COLLECTORS = [
    GithubCollector(),
    HackerNewsCollector(),
    HuggingFaceCollector(),
    ArxivCollector(),
    ProductHuntCollector(),
]

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
}

OPPORTUNITY_NAMES = {
    "high": "高",
    "medium": "中",
    "low": "低",
}


def collect_sources():
    items = []

    for collector in COLLECTORS:
        start = time.time()
        try:
            data = collector.collect_safe()
            if not isinstance(data, list):
                data = []

            for raw_item in data:
                if isinstance(raw_item, RadarItem):
                    items.append(raw_item)
                elif isinstance(raw_item, dict):
                    items.append(RadarItem.from_dict(raw_item))

            logger.info(
                "collector=%s items=%s duration=%.2fs",
                collector.__class__.__name__,
                len(data),
                time.time() - start,
            )
        except Exception:
            logger.exception(
                "collector failed=%s duration=%.2fs",
                collector.__class__.__name__,
                time.time() - start,
            )

    return items


def fallback_analysis(item, error=None):
    return {
        "summary": "AI 分析暂不可用，建议直接查看项目页面了解最新进展。",
        "trend_score": item.trend_score or 50,
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "error": str(error) if error else None,
    }


def _is_recent_item(item: RadarItem) -> bool:
    hours = age_hours(item.to_dict())
    if hours is None:
        return False
    return hours <= MAX_PROJECT_AGE_DAYS * 24


def build_report(items):
    """Score all recent items first, then analyze only the final Top 10."""
    scored = []

    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)

        if not _is_recent_item(item):
            continue

        item.trend_score = calculate_score(item.to_dict())
        scored.append(item)

    scored.sort(key=lambda x: x.trend_score, reverse=True)
    candidates = scored[:MAX_REPORT_ITEMS]

    for item in candidates:
        try:
            item.analysis = analyze_item(item.to_dict()) or {}
        except Exception as error:
            logger.exception("analysis failed item=%s", item.title)
            item.analysis = fallback_analysis(item, error)

    return candidates


def filter_existing_items(db, items):
    return [item for item in items if not item.url or not exists(db, item.url)]


def _format_age(item: RadarItem) -> str:
    hours = age_hours(item.to_dict())
    if hours is None:
        return "上线时间未知"
    if hours < 1:
        return "1 小时内上线"
    if hours < 24:
        return f"约 {int(hours)} 小时前上线"
    return f"约 {max(int(hours // 24), 1)} 天前上线"


def _format_metrics(item: RadarItem) -> str:
    metrics = item.metrics or {}

    if item.source == "github":
        return f"星标 {metrics.get('stars', 0)} · 分支 {metrics.get('forks', 0)}"
    if item.source in {"producthunt", "hackernews"}:
        return f"热度票 {metrics.get('upvotes', 0)} · 评论 {metrics.get('comments', 0)}"
    if item.source == "huggingface":
        return f"下载 {metrics.get('downloads', 0)} · 点赞 {metrics.get('likes', 0)}"
    if item.source == "arxiv":
        return "最新发布研究"

    return "早期增长信号"


def build_feishu_message(items):
    lines = [
        "🚀 **AI 新项目雷达｜今日早期热点**",
        "",
        f"> 本期发现 **{len(items)}** 个值得关注的新项目。",
        "> 筛选逻辑：只看最近 14 天上线项目，优先最近 7 天且单位时间增长更快的早期项目。",
        "",
    ]

    for index, item in enumerate(items, start=1):
        analysis = item.analysis or {}
        opportunity = OPPORTUNITY_NAMES.get(
            str(analysis.get("opportunity", "medium")).lower(),
            "中",
        )
        summary = analysis.get("summary") or "暂无 AI 分析摘要。"
        source_name = SOURCE_NAMES.get(item.source, item.source)

        lines.extend(
            [
                "---",
                f"**{index:02d}｜{item.title}**",
                f"📍 来源：{source_name}",
                f"🕒 {_format_age(item)}",
                f"🔥 新项目热度：**{item.trend_score:.1f}/100**",
                f"📈 早期信号：{_format_metrics(item)}",
                f"💼 商业机会：**{opportunity}**",
                f"🧠 AI 判断：{summary}",
                f"🔗 [查看项目]({item.url})" if item.url else "🔗 暂无项目链接",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "*说明：这里的“热度”强调早期增长速度，不代表历史累计热度。*",
        ]
    )

    return "\n".join(lines)


def _execute_daily_radar(execution_id: str, started: float):
    init_database()

    items = collect_sources()
    cleaned = normalize_items([item.to_dict() for item in items])
    radar_items = [RadarItem.from_dict(item) for item in cleaned]

    db = SessionLocal()
    report = []
    saved_count = 0

    try:
        new_items = filter_existing_items(db, radar_items)
        report = build_report(new_items)
        saved_records = save_batch(db, [item.to_dict() for item in report])
        saved_count = len(saved_records)

        if saved_count != len(report):
            logger.warning(
                "database save incomplete saved=%s requested=%s execution_id=%s",
                saved_count,
                len(report),
                execution_id,
            )
        else:
            logger.info(
                "saved=%s execution_id=%s",
                saved_count,
                execution_id,
            )
    except Exception:
        logger.exception("pipeline database stage failed execution_id=%s", execution_id)
    finally:
        db.close()

    if report:
        try:
            sent = send_feishu(build_feishu_message(report))
            if sent:
                logger.info("feishu sent execution_id=%s", execution_id)
            else:
                logger.warning("feishu not sent execution_id=%s", execution_id)
        except Exception:
            logger.exception("feishu failed execution_id=%s", execution_id)

    duration = round(time.time() - started, 2)
    logger.info(
        "daily radar finished execution_id=%s duration=%ss items=%s saved=%s",
        execution_id,
        duration,
        len(report),
        saved_count,
    )

    return {
        "execution_id": execution_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "duration": duration,
        "items": [item.to_dict() for item in report],
    }


def run_daily_radar():
    execution_id = str(uuid.uuid4())
    started = time.time()

    with execution_lock() as acquired:
        if not acquired:
            duration = round(time.time() - started, 2)
            logger.warning(
                "daily radar skipped: another execution is already running execution_id=%s",
                execution_id,
            )
            return {
                "execution_id": execution_id,
                "time": datetime.now(timezone.utc).isoformat(),
                "duration": duration,
                "items": [],
                "skipped": True,
                "reason": "already_running",
            }

        logger.info("daily radar started execution_id=%s", execution_id)
        return _execute_daily_radar(execution_id, started)

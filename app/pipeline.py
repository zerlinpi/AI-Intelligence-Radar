from datetime import datetime, timezone
import time
import uuid
from zoneinfo import ZoneInfo

from app.cleaner import normalize_items
from app.scoring import (
    age_hours,
    calculate_priority_score,
    calculate_score,
    priority_tags,
)
from app.ai.analyzer import analyze_items
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


logger = get_logger("主流程")

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
                "采集器=%s 数量=%s 耗时=%.2f秒",
                collector.__class__.__name__,
                len(data),
                time.time() - start,
            )
        except Exception:
            logger.exception(
                "采集失败：采集器=%s 耗时=%.2f秒",
                collector.__class__.__name__,
                time.time() - start,
            )

    return items


def fallback_analysis(item, error=None):
    return {
        "purpose": "项目用途暂无法生成，请查看项目原始说明。",
        "summary": "AI 分析暂不可用，建议直接查看项目页面了解最新进展。",
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
    """先算热度与业务优先级，再批量分析最终前 10 条。"""
    scored = []

    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)

        if not _is_recent_item(item):
            continue

        item_data = item.to_dict()
        item.trend_score = calculate_score(item_data)
        item_data["trend_score"] = item.trend_score

        tags = priority_tags(item_data)
        priority_score = calculate_priority_score(item_data)

        item.metrics = dict(item.metrics or {})
        item.metrics["priority_tags"] = tags
        item.metrics["priority_score"] = priority_score
        item.metrics["selection_score"] = round(
            item.trend_score + priority_score,
            2,
        )
        scored.append(item)

    scored.sort(
        key=lambda x: (
            (x.metrics or {}).get("selection_score", x.trend_score),
            x.trend_score,
        ),
        reverse=True,
    )
    candidates = scored[:MAX_REPORT_ITEMS]

    if not candidates:
        return []

    try:
        analyses = analyze_items([item.to_dict() for item in candidates])
        for item, analysis in zip(candidates, analyses):
            item.analysis = analysis or fallback_analysis(item)
    except Exception as error:
        logger.exception("AI 批量分析失败，本轮使用降级结果")
        for item in candidates:
            item.analysis = fallback_analysis(item, error)

    return candidates


def filter_existing_items(db, items):
    return [item for item in items if not item.url or not exists(db, item.url)]


def _format_age(item: RadarItem) -> str:
    hours = age_hours(item.to_dict())
    if hours is None:
        return "时间未知"
    if hours < 1:
        return "1小时内"
    if hours < 24:
        return f"{int(hours)}小时前"
    return f"{max(int(hours // 24), 1)}天前"


def _number(value) -> float:
    try:
        return max(float(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _per_day(item: RadarItem, value) -> float:
    hours = age_hours(item.to_dict())
    age_days = max((hours if hours is not None else 24) / 24, 0.25)
    return _number(value) / age_days


def _format_rate(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _format_metrics(item: RadarItem) -> str:
    metrics = item.metrics or {}

    if item.source == "github":
        stars = metrics.get("stars", 0)
        forks = metrics.get("forks", 0)
        rate = _format_rate(_per_day(item, stars))
        return f"⭐ {stars} · Fork {forks} · +{rate} 星/天"

    if item.source in {"producthunt", "hackernews"}:
        upvotes = metrics.get("upvotes", 0)
        comments = metrics.get("comments", 0)
        rate = _format_rate(_per_day(item, upvotes))
        return f"▲ {upvotes} 票 · 评论 {comments} · +{rate} 票/天"

    if item.source == "huggingface":
        downloads = metrics.get("downloads", 0)
        likes = metrics.get("likes", 0)
        rate = _format_rate(_per_day(item, downloads))
        return f"下载 {downloads} · 点赞 {likes} · +{rate}/天"

    if item.source == "arxiv":
        return "最新发布研究"

    return "出现早期增长信号"


def _report_date() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%m月%d日")


def _clean_text(value, fallback: str = "") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _format_priority_tags(item: RadarItem) -> str:
    tags = (item.metrics or {}).get("priority_tags") or []
    if not isinstance(tags, list):
        return ""
    clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    return " · ".join(clean_tags)


def build_feishu_message(items):
    lines = [
        f"**{_report_date()} · 今日发现 {len(items)} 个新项目**",
        "> 优先：跨境电商相关 · 可产品化 · 7 天内快速升温",
        "",
    ]

    for index, item in enumerate(items, start=1):
        analysis = item.analysis or {}
        opportunity = OPPORTUNITY_NAMES.get(
            str(analysis.get("opportunity", "medium")).lower(),
            "中",
        )
        business_score = _number(analysis.get("business_score", 0))
        purpose = _clean_text(
            analysis.get("purpose"),
            "项目用途暂不明确。",
        )
        summary = _clean_text(
            analysis.get("summary"),
            "暂无 AI 分析摘要。",
        )
        source_name = SOURCE_NAMES.get(item.source, item.source)
        priority_text = _format_priority_tags(item)
        ideas = analysis.get("startup_ideas") or []
        first_idea = _clean_text(ideas[0]) if isinstance(ideas, list) and ideas else ""

        title_line = f"**{index:02d}｜{item.title}**"
        if item.url:
            title_line += f"  [查看 →]({item.url})"

        lines.extend(
            [
                title_line,
                (
                    f"`{source_name}` · {_format_age(item)}"
                    f"　🔥 **{item.trend_score:.0f}**"
                    f"　💼 **{business_score:.0f} · {opportunity}**"
                ),
            ]
        )

        if priority_text:
            lines.append(f"🎯 {priority_text}")

        lines.extend(
            [
                f"🧩 **做什么：** {purpose}",
                f"📈 {_format_metrics(item)}",
                f"🧠 **值得看：** {summary}",
            ]
        )

        if first_idea:
            lines.append(f"💡 **产品机会：** {first_idea}")

        if index != len(items):
            lines.extend(["", "---", ""])

    lines.extend(
        [
            "",
            "*热度只代表早期增长速度；排序额外优先跨境电商相关和可产品化项目。*",
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
        logger.info(
            "去重完成：采集=%s 新项目=%s",
            len(radar_items),
            len(new_items),
        )

        report = build_report(new_items)
        saved_records = save_batch(db, [item.to_dict() for item in report])
        saved_count = len(saved_records)

        if saved_count != len(report):
            logger.warning(
                "数据库保存不完整：成功=%s 计划=%s 执行编号=%s",
                saved_count,
                len(report),
                execution_id,
            )
        else:
            logger.info(
                "数据库保存完成：数量=%s 执行编号=%s",
                saved_count,
                execution_id,
            )
    except Exception:
        logger.exception("数据库阶段失败：执行编号=%s", execution_id)
    finally:
        db.close()

    if report:
        try:
            sent = send_feishu(build_feishu_message(report))
            if sent:
                logger.info("飞书通知发送成功：执行编号=%s", execution_id)
            else:
                logger.warning("飞书通知未发送：执行编号=%s", execution_id)
        except Exception:
            logger.exception("飞书通知发送失败：执行编号=%s", execution_id)

    duration = round(time.time() - started, 2)
    logger.info(
        "日报执行完成：执行编号=%s 耗时=%s秒 报告=%s 保存=%s",
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
                "日报跳过：已有任务正在运行，执行编号=%s",
                execution_id,
            )
            return {
                "execution_id": execution_id,
                "time": datetime.now(timezone.utc).isoformat(),
                "duration": duration,
                "items": [],
                "skipped": True,
                "reason": "已有任务正在运行",
            }

        logger.info("日报开始执行：执行编号=%s", execution_id)
        return _execute_daily_radar(execution_id, started)

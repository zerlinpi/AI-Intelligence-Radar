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
from app.sources.policies import PolicyCollector

from app.database.session import SessionLocal, init_database
from app.storage.repository import save_batch, exists


logger = get_logger("主流程")

MAX_REPORT_ITEMS = 10
MAX_POLICY_ITEMS = 3
MAX_PROJECT_AGE_DAYS = 14

COLLECTORS = [
    GithubCollector(),
    HackerNewsCollector(),
    HuggingFaceCollector(),
    ArxivCollector(),
    ProductHuntCollector(),
]
POLICY_COLLECTOR = PolicyCollector()

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
    "amazon_policy": "Amazon",
    "tiktok_policy": "TikTok Shop",
    "us_regulation": "美国跨境法规",
}

OPPORTUNITY_NAMES = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

RISK_MARKERS = {
    "high": "🔴 高",
    "medium": "🟠 中",
    "low": "🟢 低",
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


def collect_policies():
    start = time.time()
    try:
        data = POLICY_COLLECTOR.collect_safe(MAX_POLICY_ITEMS * 3)
        items = []
        for raw_item in data if isinstance(data, list) else []:
            if isinstance(raw_item, RadarItem):
                items.append(raw_item)
            elif isinstance(raw_item, dict):
                items.append(RadarItem.from_dict(raw_item))

        logger.info(
            "政策采集：数量=%s 耗时=%.2f秒",
            len(items),
            time.time() - start,
        )
        return items
    except Exception:
        logger.exception("政策采集失败：耗时=%.2f秒", time.time() - start)
        return []


def fallback_analysis(item, error=None):
    if getattr(item, "category", "") == "policy":
        return {
            "purpose": "政策内容暂无法生成，请查看官方原文。",
            "summary": "影响判断暂不可用，建议优先核对政策适用范围。",
            "business_score": 50,
            "opportunity": "medium",
            "startup_ideas": ["查看原文并核对账号与商品影响"],
            "error": str(error) if error else None,
        }

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


def select_project_candidates(items):
    """根据早期热度与业务优先级选出最终项目，不调用模型。"""
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
    return scored[:MAX_REPORT_ITEMS]


def select_policy_candidates(items):
    """选出最新且最相关的政策规则，不调用模型。"""
    policies = []
    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)
        if item.category != "policy":
            continue
        policies.append(item)

    policies.sort(
        key=lambda x: (
            (x.metrics or {}).get("policy_score", 0),
            x.created_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return policies[:MAX_POLICY_ITEMS]


def analyze_digest(projects, policies):
    """政策与项目共用一次 DeepSeek 批量请求。"""
    combined = list(policies or []) + list(projects or [])
    if not combined:
        return

    try:
        analyses = analyze_items([item.to_dict() for item in combined])
        for item, analysis in zip(combined, analyses):
            item.analysis = analysis or fallback_analysis(item)
    except Exception as error:
        logger.exception("AI 批量分析失败，本轮使用降级结果")
        for item in combined:
            item.analysis = fallback_analysis(item, error)


def build_report(items):
    """兼容旧调用：构建并分析项目报告。"""
    candidates = select_project_candidates(items)
    analyze_digest(candidates, [])
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


def _is_cross_border_project(item: RadarItem) -> bool:
    return "跨境电商" in ((item.metrics or {}).get("priority_tags") or [])


def _append_policy_section(lines, policies):
    lines.append("**🚨 先处理｜政策与规则**")

    if not policies:
        lines.extend([
            "今日未发现新增的高影响平台政策或跨境规则。",
            "",
        ])
        return

    for index, item in enumerate(policies, start=1):
        analysis = item.analysis or {}
        urgency = str(analysis.get("opportunity", "medium")).lower()
        marker = RISK_MARKERS.get(urgency, "🟠 中")
        impact_score = _number(analysis.get("business_score", 50))
        change = _clean_text(analysis.get("purpose"), item.description)
        impact = _clean_text(analysis.get("summary"), "请查看官方原文确认影响。")
        ideas = analysis.get("startup_ideas") or []
        action = _clean_text(ideas[0]) if isinstance(ideas, list) and ideas else ""
        source_name = (item.metrics or {}).get("policy_source") or SOURCE_NAMES.get(item.source, item.source)

        title = f"**{index:02d}｜{source_name}｜{item.title}**"
        if item.url:
            title += f"  [原文 →]({item.url})"

        lines.extend([
            title,
            f"{marker} · 影响 **{impact_score:.0f}/100** · {_format_age(item)}",
            f"**变化：** {change}",
            f"**影响：** {impact}",
        ])
        if action:
            lines.append(f"**动作：** {action}")

        if index != len(policies):
            lines.append("")

    lines.extend(["", "---", ""])


def _append_project_group(lines, title, items, start_index=1):
    if not items:
        return start_index

    lines.append(f"**{title}**")

    for offset, item in enumerate(items):
        index = start_index + offset
        analysis = item.analysis or {}
        opportunity = OPPORTUNITY_NAMES.get(
            str(analysis.get("opportunity", "medium")).lower(),
            "中",
        )
        business_score = _number(analysis.get("business_score", 0))
        purpose = _clean_text(analysis.get("purpose"), "项目用途暂不明确。")
        summary = _clean_text(analysis.get("summary"), "暂无 AI 分析摘要。")
        source_name = SOURCE_NAMES.get(item.source, item.source)
        priority_text = _format_priority_tags(item)
        ideas = analysis.get("startup_ideas") or []
        first_idea = _clean_text(ideas[0]) if isinstance(ideas, list) and ideas else ""

        title_line = f"**{index:02d}｜{item.title}**"
        if item.url:
            title_line += f"  [查看 →]({item.url})"

        lines.extend([
            title_line,
            (
                f"`{source_name}` · {_format_age(item)}"
                f"　🔥 **{item.trend_score:.0f}**"
                f"　💼 **{business_score:.0f} · {opportunity}**"
            ),
        ])

        if priority_text:
            lines.append(f"🎯 {priority_text}")

        lines.extend([
            f"**做什么：** {purpose}",
            f"📈 {_format_metrics(item)}",
            f"**为什么看：** {summary}",
        ])

        if first_idea:
            lines.append(f"**可做产品：** {first_idea}")

        if offset != len(items) - 1:
            lines.append("")

    lines.extend(["", "---", ""])
    return start_index + len(items)


def build_feishu_message(items, policies=None):
    policies = list(policies or [])
    items = list(items or [])
    cross_border = [item for item in items if _is_cross_border_project(item)]
    other = [item for item in items if not _is_cross_border_project(item)]

    lines = [
        f"**{_report_date()} · 跨境 AI 情报简报**",
        (
            f"> 今日：{len(policies)} 条政策变化 · "
            f"{len(cross_border)} 个跨境机会 · {len(other)} 个其他产品化信号"
        ),
        "> 阅读顺序：先处理风险，再看增长机会。",
        "",
    ]

    _append_policy_section(lines, policies)

    next_index = _append_project_group(
        lines,
        "🎯 优先看｜跨境电商机会",
        cross_border,
        1,
    )
    _append_project_group(
        lines,
        "🧪 再观察｜其他可产品化信号",
        other,
        next_index,
    )

    if lines[-3:] == ["", "---", ""]:
        del lines[-3:]

    lines.extend([
        "",
        "*政策以官方原文为准；热度代表早期增长速度，项目排序额外优先跨境电商与可产品化价值。*",
    ])

    return "\n".join(lines)


def _execute_daily_radar(execution_id: str, started: float):
    init_database()

    items = collect_sources()
    policy_items = collect_policies()

    cleaned = normalize_items([item.to_dict() for item in items])
    radar_items = [RadarItem.from_dict(item) for item in cleaned]

    db = SessionLocal()
    report = []
    policy_report = []
    saved_count = 0

    try:
        new_items = filter_existing_items(db, radar_items)
        new_policies = filter_existing_items(db, policy_items)
        logger.info(
            "去重完成：项目=%s 新项目=%s 政策=%s 新政策=%s",
            len(radar_items),
            len(new_items),
            len(policy_items),
            len(new_policies),
        )

        report = select_project_candidates(new_items)
        policy_report = select_policy_candidates(new_policies)
        analyze_digest(report, policy_report)

        to_save = [item.to_dict() for item in policy_report + report]
        saved_records = save_batch(db, to_save)
        saved_count = len(saved_records)

        if saved_count != len(to_save):
            logger.warning(
                "数据库保存不完整：成功=%s 计划=%s 执行编号=%s",
                saved_count,
                len(to_save),
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

    if report or policy_report:
        try:
            sent = send_feishu(build_feishu_message(report, policy_report))
            if sent:
                logger.info("飞书通知发送成功：执行编号=%s", execution_id)
            else:
                logger.warning("飞书通知未发送：执行编号=%s", execution_id)
        except Exception:
            logger.exception("飞书通知发送失败：执行编号=%s", execution_id)

    duration = round(time.time() - started, 2)
    logger.info(
        "日报执行完成：执行编号=%s 耗时=%s秒 项目=%s 政策=%s 保存=%s",
        execution_id,
        duration,
        len(report),
        len(policy_report),
        saved_count,
    )

    return {
        "execution_id": execution_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "duration": duration,
        "items": [item.to_dict() for item in report],
        "policies": [item.to_dict() for item in policy_report],
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
                "policies": [],
                "skipped": True,
                "reason": "已有任务正在运行",
            }

        logger.info("日报开始执行：执行编号=%s", execution_id)
        return _execute_daily_radar(execution_id, started)

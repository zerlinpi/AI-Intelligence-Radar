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
MAX_POLICY_ITEMS = 4
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
    "us_import_rule": "美国海关 CBP",
    "cpsc_compliance": "CPSC",
    "fda_compliance": "FDA",
    "fcc_compliance": "FCC",
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

POLICY_FOCUS_ORDER = (
    "Amazon政策与审核",
    "美国跨境新规",
    "产品合规审核",
)


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
        data = POLICY_COLLECTOR.collect_safe(MAX_POLICY_ITEMS * 4)
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
            "purpose": "政策或审核要求暂无法生成，请查看官方原文。",
            "summary": "影响范围暂不可用，建议核对产品类别、进口主体与适用法规。",
            "affected_products": "请依据官方原文核对具体适用产品、功能特征与豁免范围。",
            "risk": "AI 风险拆分未完成；在确认适用范围前，不应假设现有产品已经满足准入要求。",
            "preparation": "先保存官方原文，并核对相关测试、证书、注册、标签或申报资料。",
            "business_score": 50,
            "opportunity": "medium",
            "startup_ideas": ["核对官方原文并准备对应合规资料"],
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
    """根据早期热度与跨境业务优先级选出最终项目。"""
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


def _policy_focus(item: RadarItem) -> str:
    return str((item.metrics or {}).get("policy_focus") or "").strip()


def select_policy_candidates(items):
    """优先保证 Amazon、进口新规、产品审核三类情报都能进入日报。"""
    policies = []
    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)
        if item.category == "policy":
            policies.append(item)

    policies.sort(
        key=lambda x: (
            (x.metrics or {}).get("policy_score", 0),
            x.created_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    selected = []
    selected_ids = set()

    # 先从每一类取最高优先级的一条，避免全部名额被单个平台占满。
    for focus in POLICY_FOCUS_ORDER:
        match = next((item for item in policies if _policy_focus(item) == focus), None)
        if match is not None:
            selected.append(match)
            selected_ids.add(id(match))

    # 剩余名额再按总体政策分补齐。
    for item in policies:
        if len(selected) >= MAX_POLICY_ITEMS:
            break
        if id(item) in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(id(item))

    selected.sort(
        key=lambda x: (
            POLICY_FOCUS_ORDER.index(_policy_focus(x))
            if _policy_focus(x) in POLICY_FOCUS_ORDER
            else 99,
            -float((x.metrics or {}).get("policy_score", 0) or 0),
        )
    )
    return selected[:MAX_POLICY_ITEMS]


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


def _clip_text(value, limit: int = 180) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _format_priority_tags(item: RadarItem) -> str:
    tags = (item.metrics or {}).get("priority_tags") or []
    if not isinstance(tags, list):
        return ""
    clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    return " · ".join(clean_tags)


def _is_cross_border_project(item: RadarItem) -> bool:
    return "跨境电商" in ((item.metrics or {}).get("priority_tags") or [])


def _policy_group_title(focus: str) -> str:
    return {
        "Amazon政策与审核": "**A｜Amazon 政策与审核**",
        "美国跨境新规": "**B｜美国跨境进口新规**",
        "产品合规审核": "**C｜美国市场产品审核**",
    }.get(focus, "**其他合规变化**")


def _policy_field_labels(focus: str):
    if focus == "美国跨境新规":
        return "新规要点", "进口影响", "建议动作"
    return "核心变化", "卖家影响", "建议动作"


def _product_compliance_brief(group):
    """为美国市场产品审核板块生成可扫描的决策简报，不额外调用模型。"""
    if not group:
        return []

    authorities = []
    affected = []
    preparations = []
    highest_item = None
    highest_score = -1

    for item in group:
        metrics = item.metrics or {}
        authority = _clean_text(metrics.get("policy_authority"))
        if authority and authority not in authorities:
            authorities.append(authority)

        analysis = item.analysis or {}
        product_text = _clean_text(analysis.get("affected_products"))
        if product_text and product_text not in affected:
            affected.append(product_text)

        prep_text = _clean_text(analysis.get("preparation"))
        if prep_text and prep_text not in preparations:
            preparations.append(prep_text)

        score = _number(analysis.get("business_score", 50))
        if score > highest_score:
            highest_score = score
            highest_item = item

    highest_analysis = (highest_item.analysis or {}) if highest_item else {}
    highest_urgency = str(highest_analysis.get("opportunity", "medium")).lower()
    highest_marker = RISK_MARKERS.get(highest_urgency, "🟠 中")

    scope = " / ".join(authorities) if authorities else "美国市场准入机构"
    lines = [
        (
            f"> **审核简报：** 今日共 **{len(group)} 条**产品准入/合规审核，"
            f"涉及 **{scope}**；最高风险 **{highest_marker}**，优先处理高影响产品的准入资料完整性。"
        )
    ]

    if affected:
        lines.append(
            f"> 🎯 **重点影响产品：** **{_clip_text('；'.join(affected), 220)}**"
        )
    if preparations:
        lines.append(
            f"> 📋 **优先准备：** **{_clip_text('；'.join(preparations), 220)}**"
        )

    return lines


def _append_policy_section(lines, policies):
    lines.append("**🚨 今日合规重点**")

    if not policies:
        lines.extend([
            "今日未发现新增的高影响 Amazon 政策、美国跨境新规或产品审核要求。",
            "",
        ])
        return

    display_index = 1
    for focus in POLICY_FOCUS_ORDER:
        group = [item for item in policies if _policy_focus(item) == focus]
        if not group:
            continue

        lines.extend(["", _policy_group_title(focus), ""])
        if focus == "产品合规审核":
            lines.extend(_product_compliance_brief(group))
            lines.append("")

        for item in group:
            analysis = item.analysis or {}
            urgency = str(analysis.get("opportunity", "medium")).lower()
            marker = RISK_MARKERS.get(urgency, "🟠 中")
            impact_score = _number(analysis.get("business_score", 50))
            purpose = _clean_text(analysis.get("purpose"), item.description)
            impact = _clean_text(
                analysis.get("summary"),
                "请查看官方原文确认适用范围与影响。",
            )
            ideas = analysis.get("startup_ideas") or []
            action = _clean_text(ideas[0]) if isinstance(ideas, list) and ideas else ""
            metrics = item.metrics or {}
            source_name = metrics.get("policy_source") or SOURCE_NAMES.get(item.source, item.source)
            authority = metrics.get("policy_authority") or ""
            kind = metrics.get("policy_kind") or ""

            title = f"**{display_index:02d}｜{source_name}｜{item.title}**"
            if item.url:
                title += f"  [官方信息 →]({item.url})"

            meta_parts = [part for part in (authority, kind, _format_age(item)) if part]
            lines.extend([
                title,
                f"{marker} · 影响 **{impact_score:.0f}/100** · {' · '.join(meta_parts)}",
            ])

            if focus == "产品合规审核":
                affected_products = _clean_text(
                    analysis.get("affected_products"),
                    "需依据官方原文确认具体产品类别、功能特征与豁免范围。",
                )
                risk = _clean_text(analysis.get("risk"), impact)
                preparation = _clean_text(
                    analysis.get("preparation"),
                    action or "需依据官方要求整理适用的测试、证书、注册、标签或申报资料。",
                )
                lines.extend([
                    f"**审核要求：** {purpose}",
                    f"> 🎯 **影响产品：** **{affected_products}**",
                    f"> ⚠️ **风险：** **{risk}**",
                    f"> 📋 **准备资料：** **{preparation}**",
                ])
                if action:
                    lines.append(f"**建议动作：** {action}")
            else:
                field1, field2, field3 = _policy_field_labels(focus)
                lines.extend([
                    f"**{field1}：** {purpose}",
                    f"**{field2}：** {impact}",
                ])
                if action:
                    lines.append(f"**{field3}：** {action}")

            display_index += 1
            if item is not group[-1]:
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
            title_line += f"  [查看项目 →]({item.url})"

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
            f"**产品描述：** {purpose}",
            f"**增长信号：** {_format_metrics(item)}",
            f"**价值判断：** {summary}",
        ])

        if first_idea:
            lines.append(f"**可借鉴方向：** {first_idea}")

        if offset != len(items) - 1:
            lines.append("")

    lines.extend(["", "---", ""])
    return start_index + len(items)


def build_feishu_message(items, policies=None):
    policies = list(policies or [])
    items = list(items or [])
    cross_border = [item for item in items if _is_cross_border_project(item)]
    other = [item for item in items if not _is_cross_border_project(item)]

    amazon_count = sum(1 for item in policies if _policy_focus(item) == "Amazon政策与审核")
    import_count = sum(1 for item in policies if _policy_focus(item) == "美国跨境新规")
    compliance_count = sum(1 for item in policies if _policy_focus(item) == "产品合规审核")

    lines = [
        f"**{_report_date()} · 美国跨境经营雷达**",
        (
            f"> Amazon {amazon_count} · 美国新规 {import_count} · "
            f"产品审核 {compliance_count} · 新项目 {len(items)}"
        ),
        "> 优先级：先确认合规与准入风险，再看跨境产品机会。",
        "",
    ]

    _append_policy_section(lines, policies)

    next_index = _append_project_group(
        lines,
        "🎯 跨境电商直接相关项目",
        cross_border,
        1,
    )
    _append_project_group(
        lines,
        "🧪 其他可产品化 AI 信号",
        other,
        next_index,
    )

    if lines[-3:] == ["", "---", ""]:
        del lines[-3:]

    lines.extend([
        "",
        "*合规信息以 Amazon、CBP、CPSC、FDA、FCC 等官方要求为准；项目热度仅代表早期增长速度。*",
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

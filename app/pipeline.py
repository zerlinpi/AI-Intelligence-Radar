from datetime import datetime, timezone
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.ai.analyzer import analyze_items
from app.cards import build_daily_cards
from app.cards.models import (
    ActionItem,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)
from app.cleaner import normalize_items
from app.config import FEISHU_PROJECTS_PER_CARD, REPORT_TIMEZONE
from app.core.logger import get_logger
from app.core.preflight import run_preflight
from app.core.run_lock import execution_lock
from app.database.session import SessionLocal, init_database
from app.feishu import send_feishu_cards
from app.models.radar_item import RadarItem
from app.scoring import (
    age_hours,
    calculate_priority_score,
    calculate_score,
    priority_tags,
)
from app.sources.arxiv import ArxivCollector
from app.sources.github import GithubCollector
from app.sources.hackernews import HackerNewsCollector
from app.sources.huggingface import HuggingFaceCollector
from app.sources.policies import PolicyCollector
from app.sources.producthunt import ProductHuntCollector
from app.storage.repository import exists, save_batch


logger = get_logger("主流程")

MAX_REPORT_ITEMS = 10
MAX_POLICY_ITEMS = 4
MAX_PROJECT_AGE_DAYS = 14
MAX_ITEMS_PER_SOURCE = 6
MIN_STRATEGIC_PRIORITY_SCORE = 20
MIN_STRATEGIC_SELECTION_SCORE = 35
STRATEGIC_TAGS = (
    "跨境电商",
    "技术前沿",
    "硬件开发",
    "实体商品机会",
)

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

POLICY_FOCUS_ORDER = (
    "Amazon政策与审核",
    "美国跨境新规",
    "产品合规审核",
)

RISK_ORDER = {
    "high": 3,
    "medium": 2,
    "low": 1,
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
    reason = str(error) if error else "AI 结构化分析未完成"
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
            "error": reason,
            "llm_meta": {"success": False, "fallback": True, "reason": reason},
        }

    original = " ".join(str(getattr(item, "description", "") or "").split())
    return {
        "purpose": f"项目原始说明：{original}" if original else "项目原始说明不足。",
        "summary": "AI 深度分析未完成，可先结合原始说明与增长信号判断是否继续跟进。",
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "error": reason,
        "llm_meta": {"success": False, "fallback": True, "reason": reason},
    }


def _analysis_is_fallback(analysis) -> bool:
    if not isinstance(analysis, dict):
        return True
    meta = analysis.get("llm_meta") or {}
    if isinstance(meta, dict) and meta.get("fallback") is True:
        return True
    return bool(analysis.get("error"))


def _is_recent_item(item: RadarItem) -> bool:
    hours = age_hours(item.to_dict())
    if hours is None:
        return False
    return hours <= MAX_PROJECT_AGE_DAYS * 24


def _project_selection_score(trend_score: float, priority_score: float) -> float:
    """趋势决定“现在是否值得看”，机会价值决定“是否值得做”。后者略高权重。"""
    return round(float(trend_score or 0) * 0.45 + float(priority_score or 0) * 0.55, 2)


def _portfolio_candidates(scored):
    """从高质量候选中构建多方向机会组合，避免同一来源/同一形态占满日报。

    先为四个战略方向各保留一个达到质量阈值的代表，再按综合分补齐；
    单一来源优先不超过 MAX_ITEMS_PER_SOURCE，若候选不足则第二轮解除来源上限补满。
    """
    ordered = sorted(
        scored,
        key=lambda x: (
            (x.metrics or {}).get("selection_score", 0),
            (x.metrics or {}).get("priority_score", 0),
            x.trend_score,
        ),
        reverse=True,
    )

    selected = []
    selected_ids = set()
    source_counts = {}

    def add(item):
        marker = id(item)
        if marker in selected_ids or len(selected) >= MAX_REPORT_ITEMS:
            return False
        selected.append(item)
        selected_ids.add(marker)
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        return True

    # 先保证有质量的战略方向不会被大量同质化热门项目淹没。
    for tag in STRATEGIC_TAGS:
        candidate = next(
            (
                item
                for item in ordered
                if tag in ((item.metrics or {}).get("priority_tags") or [])
                and float((item.metrics or {}).get("priority_score", 0) or 0)
                >= MIN_STRATEGIC_PRIORITY_SCORE
                and float((item.metrics or {}).get("selection_score", 0) or 0)
                >= MIN_STRATEGIC_SELECTION_SCORE
                and id(item) not in selected_ids
            ),
            None,
        )
        if candidate is not None:
            add(candidate)

    # 第一轮按来源软上限填充，优先让 GitHub、Hugging Face、arXiv、Product Hunt/HN
    # 都有机会进入最终 10 项，但不会牺牲明显的质量差距。
    for item in ordered:
        if len(selected) >= MAX_REPORT_ITEMS:
            break
        if id(item) in selected_ids:
            continue
        if source_counts.get(item.source, 0) >= MAX_ITEMS_PER_SOURCE:
            continue
        add(item)

    # 候选不足时解除来源上限，只按质量补满，不为了多样性空置名额。
    for item in ordered:
        if len(selected) >= MAX_REPORT_ITEMS:
            break
        add(item)

    selected.sort(
        key=lambda x: (
            (x.metrics or {}).get("selection_score", 0),
            (x.metrics or {}).get("priority_score", 0),
            x.trend_score,
        ),
        reverse=True,
    )
    return selected


def select_project_candidates(items):
    """按趋势、业务/技术机会和组合多样性选出最终项目。"""
    scored = []

    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)
        if not _is_recent_item(item):
            continue

        item_data = item.to_dict()
        item.trend_score = calculate_score(item_data)
        item_data["trend_score"] = item.trend_score

        # priority_tags/calculate_priority_score 会把四维机会、商品品类和证据同步写回 metrics。
        tags = priority_tags(item_data)
        priority_score = calculate_priority_score(item_data)
        item.metrics = dict(item.metrics or {})
        item.metrics["priority_tags"] = tags
        item.metrics["priority_score"] = priority_score
        item.metrics["selection_score"] = _project_selection_score(
            item.trend_score,
            priority_score,
        )
        scored.append(item)

    selected = _portfolio_candidates(scored)
    tag_counts = {
        tag: sum(
            1
            for item in selected
            if tag in ((item.metrics or {}).get("priority_tags") or [])
        )
        for tag in STRATEGIC_TAGS
    }
    source_counts = {}
    for item in selected:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1

    logger.info(
        "项目筛选：候选=%s 入选=%s 方向=%s 来源=%s",
        len(scored),
        len(selected),
        tag_counts,
        source_counts,
    )
    return selected


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
    for focus in POLICY_FOCUS_ORDER:
        match = next((item for item in policies if _policy_focus(item) == focus), None)
        if match is not None:
            selected.append(match)
            selected_ids.add(id(match))

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
    """政策与项目共用一次 DeepSeek 批量请求，并保证每条输入都有结果。"""
    combined = list(policies or []) + list(projects or [])
    if not combined:
        return

    try:
        analyses = analyze_items([item.to_dict() for item in combined])
        analyses = analyses if isinstance(analyses, list) else []
        for index, item in enumerate(combined):
            analysis = analyses[index] if index < len(analyses) else None
            item.analysis = analysis if isinstance(analysis, dict) and analysis else fallback_analysis(
                item,
                f"模型结果缺少第 {index + 1} 条",
            )
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
    try:
        zone = ZoneInfo(REPORT_TIMEZONE)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Shanghai")
    return datetime.now(zone).strftime("%m月%d日")


def _clean_text(value, fallback: str = "") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _analysis_action(analysis: dict) -> str:
    ideas = analysis.get("startup_ideas") or []
    if isinstance(ideas, list) and ideas:
        return _clean_text(ideas[0])
    return ""


def _normalized_level(value) -> str:
    level = str(value or "medium").strip().lower()
    return level if level in RISK_ORDER else "medium"


def _is_cross_border_project(item: RadarItem) -> bool:
    return "跨境电商" in ((item.metrics or {}).get("priority_tags") or [])


def _to_compliance_decision(item: RadarItem) -> ComplianceDecision:
    analysis = item.analysis or {}
    metrics = item.metrics or {}
    focus = _policy_focus(item)
    impact = _clean_text(
        analysis.get("summary"),
        "请查看官方原文确认适用范围与影响。",
    )
    action = _analysis_action(analysis)

    return ComplianceDecision(
        focus=focus,
        title=item.title,
        source_name=_clean_text(
            metrics.get("policy_source"),
            SOURCE_NAMES.get(item.source, item.source),
        ),
        authority=_clean_text(metrics.get("policy_authority")),
        kind=_clean_text(metrics.get("policy_kind")),
        age_text=_format_age(item),
        url=item.url,
        risk_level=_normalized_level(analysis.get("opportunity")),
        impact_score=_number(analysis.get("business_score", 50)),
        requirement=_clean_text(analysis.get("purpose"), item.description),
        impact=impact,
        affected_products=(
            _clean_text(
                analysis.get("affected_products"),
                "需依据官方原文确认具体适用产品与豁免范围。",
            )
            if focus == "产品合规审核"
            else ""
        ),
        risk=(
            _clean_text(analysis.get("risk"), impact)
            if focus == "产品合规审核"
            else ""
        ),
        preparation=(
            _clean_text(
                analysis.get("preparation"),
                action or "按官方要求整理对应测试、证书、注册或申报资料。",
            )
            if focus == "产品合规审核"
            else ""
        ),
        action=action,
    )


def _to_product_decision(item: RadarItem) -> ProductDecision:
    analysis = item.analysis or {}
    tags = (item.metrics or {}).get("priority_tags") or []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    return ProductDecision(
        title=item.title,
        source_name=SOURCE_NAMES.get(item.source, item.source),
        age_text=_format_age(item),
        url=item.url,
        trend_score=_number(item.trend_score),
        business_score=_number(analysis.get("business_score", 0)),
        opportunity=_normalized_level(analysis.get("opportunity")),
        tags=tags,
        description=_clean_text(analysis.get("purpose"), item.description),
        growth_signal=_format_metrics(item),
        judgment=_clean_text(analysis.get("summary"), "暂无 AI 分析摘要。"),
        direction=_analysis_action(analysis),
        cross_border=_is_cross_border_project(item),
    )


def _policy_priority(decision: ComplianceDecision):
    return (
        RISK_ORDER.get(decision.risk_level, 2),
        decision.impact_score,
    )


def _build_summary_actions(compliance, products):
    ordered_policies = sorted(compliance, key=_policy_priority, reverse=True)
    high_risk = [item for item in ordered_policies if item.risk_level == "high"]
    top_product = products[0] if products else None

    if high_risk:
        first = high_risk[0]
        must_text = first.action or first.preparation or first.requirement
    elif ordered_policies:
        first = ordered_policies[0]
        must_text = "今日无新增高风险事项；完成最高影响合规变化的适用范围核对。"
    else:
        must_text = "今日无新增高影响合规事项，维持常规审核与准入资料检查。"

    if len(ordered_policies) > 1:
        second = ordered_policies[1]
        focus_text = second.action or second.impact or second.requirement
    elif ordered_policies:
        second = ordered_policies[0]
        focus_text = second.impact or second.requirement
    else:
        focus_text = "关注 Amazon、CBP、CPSC、FDA、FCC 后续新增要求。"

    if top_product:
        research_text = top_product.direction or f"研究 {top_product.title} 的产品化与业务适配价值。"
    else:
        research_text = "今日暂无达到优先展示阈值的新产品机会。"

    return [
        ActionItem(label="必须", text=must_text),
        ActionItem(label="关注", text=focus_text),
        ActionItem(label="研究", text=research_text),
    ]


def _build_daily_judgment(compliance, products) -> str:
    high_risk = [item for item in compliance if item.risk_level == "high"]
    top_policy = max(compliance, key=_policy_priority) if compliance else None
    top_product = products[0] if products else None

    if high_risk:
        authority = (
            top_policy.authority or top_policy.source_name
            if top_policy
            else "美国合规"
        )
        base = f"发现 {len(high_risk)} 项高风险合规变化，先处理 {authority} 相关准入或审核要求。"
    elif compliance:
        base = "今日有合规变化，但未发现新增高风险事项；先确认适用范围和资料完整性。"
    else:
        base = "今日未发现新增高风险合规事项。"

    if top_product:
        return f"{base} 产品侧优先研究 {top_product.title}。"
    return base


def build_decision_model(items, policies=None) -> ReportDecisionModel:
    """将完整 AI 分析转换为飞书展示所需的结构化决策模型。"""
    items = list(items or [])
    policies = list(policies or [])
    compliance = [_to_compliance_decision(item) for item in policies]
    products = [_to_product_decision(item) for item in items]

    high_risk_count = sum(1 for item in compliance if item.risk_level == "high")
    opportunity_count = sum(
        1
        for item in products
        if item.opportunity == "high" or item.business_score >= 80
    )

    summary = DailySummary(
        date_text=_report_date(),
        judgment=_build_daily_judgment(compliance, products),
        actions=_build_summary_actions(compliance, products),
        metrics={
            "compliance": len(compliance),
            "high_risk": high_risk_count,
            "projects": len(products),
            "opportunities": opportunity_count,
        },
    )

    return ReportDecisionModel(
        summary=summary,
        compliance=compliance,
        products=products,
    )


def build_feishu_message(items, policies=None):
    """兼容旧调用；生产日报已经改用结构化 Card Builder。"""
    model = build_decision_model(items, policies)
    lines = [
        f"**{model.summary.date_text} · 美国跨境经营雷达**",
        f"**今日判断：** {model.summary.judgment}",
        "",
        "**🚨 今日合规重点**",
    ]

    seen_groups = set()
    for decision in model.compliance:
        if decision.focus == "Amazon政策与审核":
            group_title = "A｜Amazon 政策与审核"
        elif decision.focus == "美国跨境新规":
            group_title = "B｜美国跨境进口新规"
        else:
            group_title = "C｜美国市场产品审核"

        if group_title not in seen_groups:
            lines.extend(["", f"**{group_title}**"])
            seen_groups.add(group_title)
        lines.append(f"**{decision.source_name}｜{decision.title}**")

        if decision.focus == "产品合规审核":
            lines.extend([
                f"**审核要求：** {decision.requirement}",
                f"**影响产品：** {decision.affected_products}",
                f"**风险：** {decision.risk}",
                f"**准备资料：** {decision.preparation}",
            ])
        elif decision.focus == "美国跨境新规":
            lines.extend([
                f"**新规要点：** {decision.requirement}",
                f"**进口影响：** {decision.impact}",
            ])
        else:
            lines.extend([
                f"**核心变化：** {decision.requirement}",
                f"**卖家影响：** {decision.impact}",
            ])
        if decision.action:
            lines.append(f"**建议动作：** {decision.action}")

    cross_border = [item for item in model.products if item.cross_border]
    other = [item for item in model.products if not item.cross_border]
    for title, group in (
        ("🎯 跨境电商直接相关项目", cross_border),
        ("🧪 其他可产品化 AI 信号", other),
    ):
        if not group:
            continue
        lines.extend(["", f"**{title}**"])
        for product in group:
            lines.extend([
                f"**{product.title}**",
                f"**产品描述：** {product.description}",
                f"**增长信号：** {product.growth_signal}",
                f"**价值判断：** {product.judgment}",
            ])
            if product.direction:
                lines.append(f"**可借鉴方向：** {product.direction}")

    return "\n".join(lines)


def _base_result(execution_id: str, started: float, status: str, **extra):
    result = {
        "execution_id": execution_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "duration": round(time.time() - started, 2),
        "status": status,
        "items": [],
        "policies": [],
        "feishu_cards": 0,
        "feishu_sent": False,
        "errors": [],
    }
    result.update(extra)
    return result


def _execute_daily_radar(execution_id: str, started: float):
    errors = []

    try:
        init_database()
    except Exception as exc:
        logger.exception("数据库初始化失败：执行编号=%s", execution_id)
        return _base_result(
            execution_id,
            started,
            "failed",
            errors=[f"数据库初始化失败：{exc}"],
        )

    items = collect_sources()
    policy_items = collect_policies()

    try:
        cleaned = normalize_items([item.to_dict() for item in items])
        radar_items = [RadarItem.from_dict(item) for item in cleaned]
    except Exception as exc:
        logger.exception("数据清洗失败：执行编号=%s", execution_id)
        return _base_result(
            execution_id,
            started,
            "failed",
            errors=[f"数据清洗失败：{exc}"],
        )

    db = SessionLocal()
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
    except Exception as exc:
        db.rollback()
        db.close()
        logger.exception("数据库去重失败：执行编号=%s", execution_id)
        return _base_result(
            execution_id,
            started,
            "failed",
            errors=[f"数据库去重失败：{exc}"],
        )

    report = select_project_candidates(new_items)
    policy_report = select_policy_candidates(new_policies)
    analyze_digest(report, policy_report)

    fallback_count = sum(
        1
        for item in policy_report + report
        if _analysis_is_fallback(item.analysis)
    )
    if fallback_count:
        errors.append(f"AI 分析降级 {fallback_count} 条")

    saved_count = 0
    eligible_to_save = [
        item
        for item in policy_report + report
        if not _analysis_is_fallback(item.analysis)
    ]
    try:
        saved_records = save_batch(db, [item.to_dict() for item in policy_report + report])
        saved_count = len(saved_records)
        if saved_count != len(eligible_to_save):
            message = f"数据库保存不完整：成功={saved_count} 计划={len(eligible_to_save)}"
            logger.warning("%s 执行编号=%s", message, execution_id)
            errors.append(message)
        else:
            logger.info(
                "数据库保存完成：数量=%s 执行编号=%s",
                saved_count,
                execution_id,
            )
    except Exception as exc:
        db.rollback()
        logger.exception("数据库保存阶段失败：执行编号=%s", execution_id)
        errors.append(f"数据库保存阶段失败：{exc}")
    finally:
        db.close()

    card_count = 0
    feishu_sent = False
    try:
        decision_model = build_decision_model(report, policy_report)
        cards = build_daily_cards(
            decision_model,
            max_projects=FEISHU_PROJECTS_PER_CARD,
        )
        card_count = len(cards)
        feishu_sent = send_feishu_cards(
            cards,
            run_id=execution_id,
            durable=True,
        )
        if feishu_sent:
            logger.info(
                "飞书日报发送成功：执行编号=%s 卡片=%s",
                execution_id,
                card_count,
            )
        else:
            message = "飞书日报未全部送达，已保留持久化队列等待补发"
            logger.warning("%s：执行编号=%s 卡片=%s", message, execution_id, card_count)
            errors.append(message)
    except Exception as exc:
        logger.exception("飞书日报构建或发送失败：执行编号=%s", execution_id)
        errors.append(f"飞书日报构建或发送失败：{exc}")

    status = "success" if not errors else "partial"
    duration = round(time.time() - started, 2)
    logger.info(
        "日报执行完成：执行编号=%s 状态=%s 耗时=%s秒 项目=%s 政策=%s 保存=%s 飞书卡片=%s",
        execution_id,
        status,
        duration,
        len(report),
        len(policy_report),
        saved_count,
        card_count,
    )

    return {
        "execution_id": execution_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "duration": duration,
        "status": status,
        "items": [item.to_dict() for item in report],
        "policies": [item.to_dict() for item in policy_report],
        "feishu_cards": card_count,
        "feishu_sent": feishu_sent,
        "errors": errors,
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
                "status": "skipped",
                "items": [],
                "policies": [],
                "feishu_cards": 0,
                "feishu_sent": False,
                "errors": [],
                "skipped": True,
                "reason": "已有任务正在运行",
            }

        preflight = run_preflight()
        if not preflight.ok:
            logger.error(
                "日报预检失败，已停止执行：执行编号=%s 失败项=%s",
                execution_id,
                "、".join(preflight.failures),
            )
            return _base_result(
                execution_id,
                started,
                "failed",
                errors=[f"生产预检失败：{name}" for name in preflight.failures],
            )

        logger.info("日报开始执行：执行编号=%s", execution_id)
        try:
            return _execute_daily_radar(execution_id, started)
        except Exception as exc:
            logger.exception("日报发生未捕获异常：执行编号=%s", execution_id)
            return _base_result(
                execution_id,
                started,
                "failed",
                errors=[f"未捕获异常：{exc}"],
            )

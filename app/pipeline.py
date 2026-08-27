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
from app.content_quality import copy_similarity
from app.core.logger import get_logger
from app.core.preflight import run_preflight
from app.core.run_lock import execution_lock
from app.database.session import SessionLocal, init_database
from app.feishu import send_feishu_cards
from app.history_novelty import filter_recently_reported
from app.models.radar_item import RadarItem
from app.relevance import attach_eligibility_metrics, report_eligibility
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
from app.storage.repository import save_batch


logger = get_logger("主流程")

MAX_REPORT_ITEMS = 10
MAX_POLICY_ITEMS = 4
MAX_PROJECT_AGE_DAYS = 14
MAX_ITEMS_PER_SOURCE = 6

# 本地筛选只负责决定哪些候选值得消耗 DeepSeek Token。
MIN_REPORT_PRIORITY_SCORE = 20
MIN_REPORT_SELECTION_SCORE = 35
MIN_STRATEGIC_PRIORITY_SCORE = 20
MIN_STRATEGIC_SELECTION_SCORE = 35

# DeepSeek 前只对“明确使用场景”做保守去同质化：
# 1) 同场景原始能力说明高度相似时只保留排名更高的代表；
# 2) 同一场景最多分析 3 个不同技术路线，避免 10 条都被 Listing/Seller Agent 占满；
# 3) “其他”场景不套配额，防止粗分类误伤真正不同的新能力。
PRE_LLM_MAX_PER_USE_CASE = 3
PRE_LLM_SEMANTIC_DESCRIPTION_THRESHOLD = 0.84
PRE_LLM_MIN_DESCRIPTION_CHARS = 48

# DeepSeek 分析后再做一次最终价值裁决。论文/模型要求更高，避免纯研究信号混入日报。
FINAL_BUSINESS_SCORE = {
    "github": 65,
    "producthunt": 66,
    "hackernews": 66,
    "huggingface": 70,
    "arxiv": 72,
}
DEFAULT_FINAL_BUSINESS_SCORE = 68
FINAL_MIN_PURPOSE_CHARS = 18
FINAL_MIN_JUDGMENT_CHARS = 18
FINAL_MIN_ACTION_CHARS = 10

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


def _candidate_use_case(item: RadarItem) -> str:
    """返回可用于 DeepSeek 前组合压缩的明确场景；粗粒度“其他”不参与限额。"""
    value = str((item.metrics or {}).get("primary_use_case") or "").strip()
    if not value or value == "其他":
        return ""
    return value


def _candidate_description(item: RadarItem) -> str:
    return " ".join(str(getattr(item, "description", "") or "").split()).strip()


def _same_pre_llm_opportunity(left: RadarItem, right: RadarItem) -> bool:
    """只在同一明确场景内，用原始能力说明识别高置信同质候选。

    这里不使用标题、Star 或来源做判重，避免多个不同名字包装同一种能力绕过压缩；
    也不对短说明做语义删除，避免证据不足时误伤不同技术路线。
    """
    left_use_case = _candidate_use_case(left)
    right_use_case = _candidate_use_case(right)
    if not left_use_case or left_use_case != right_use_case:
        return False

    left_description = _candidate_description(left)
    right_description = _candidate_description(right)
    if min(len(left_description), len(right_description)) < PRE_LLM_MIN_DESCRIPTION_CHARS:
        return False

    return (
        copy_similarity(left_description, right_description)
        >= PRE_LLM_SEMANTIC_DESCRIPTION_THRESHOLD
    )


def _portfolio_candidates(scored):
    """从已经达到质量底线的候选中构建多方向机会组合。

    不为凑够 10 条降低质量门槛。DeepSeek 前先压掉同一明确使用场景的高置信重复，
    并把单场景控制在最多 3 条；空出的名额继续从其他合格场景补位。来源上限仍是软约束。
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
    use_case_counts = {}

    def can_add(item):
        if id(item) in selected_ids or len(selected) >= MAX_REPORT_ITEMS:
            return False

        use_case = _candidate_use_case(item)
        if use_case:
            if use_case_counts.get(use_case, 0) >= PRE_LLM_MAX_PER_USE_CASE:
                return False
            if any(
                _same_pre_llm_opportunity(item, existing)
                for existing in selected
                if _candidate_use_case(existing) == use_case
            ):
                return False
        return True

    def add(item):
        if not can_add(item):
            return False
        marker = id(item)
        selected.append(item)
        selected_ids.add(marker)
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        use_case = _candidate_use_case(item)
        if use_case:
            use_case_counts[use_case] = use_case_counts.get(use_case, 0) + 1
        return True

    # 战略方向代表同样遵守同质化约束；若最高分候选与已选项重复，会继续寻找下一个不同候选。
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
                and can_add(item)
            ),
            None,
        )
        if candidate is not None:
            add(candidate)

    for item in ordered:
        if len(selected) >= MAX_REPORT_ITEMS:
            break
        if id(item) in selected_ids:
            continue
        if source_counts.get(item.source, 0) >= MAX_ITEMS_PER_SOURCE:
            continue
        add(item)

    # 只解除来源上限，不解除质量/同质化门槛；ordered 本身已经全是合格候选。
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
    """本地第一道 Gate：相关性、证据、时间、机会分全部达标才进入 DeepSeek。"""
    scored = []
    rejected_relevance = 0
    rejected_score = 0

    for raw_item in items:
        item = raw_item if isinstance(raw_item, RadarItem) else RadarItem.from_dict(raw_item)
        if not _is_recent_item(item):
            continue

        item_data = item.to_dict()
        eligibility = report_eligibility(item_data)
        attach_eligibility_metrics(item_data, eligibility)
        item.metrics = dict(item_data.get("metrics") or {})
        if not eligibility.get("eligible"):
            rejected_relevance += 1
            continue

        item.trend_score = calculate_score(item_data)
        item_data["trend_score"] = item.trend_score

        tags = priority_tags(item_data)
        priority_score = calculate_priority_score(item_data)
        item.metrics = dict(item_data.get("metrics") or {})
        item.metrics["priority_tags"] = tags
        item.metrics["priority_score"] = priority_score
        item.metrics["selection_score"] = _project_selection_score(
            item.trend_score,
            priority_score,
        )

        if (
            float(priority_score or 0) < MIN_REPORT_PRIORITY_SCORE
            or float(item.metrics["selection_score"] or 0) < MIN_REPORT_SELECTION_SCORE
        ):
            rejected_score += 1
            continue

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
    use_case_counts = {}
    for item in selected:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        use_case = _candidate_use_case(item)
        if use_case:
            use_case_counts[use_case] = use_case_counts.get(use_case, 0) + 1

    logger.info(
        "项目筛选：合格候选=%s 相关性/证据淘汰=%s 分数淘汰=%s 入选DeepSeek=%s "
        "同质/组合压缩=%s 方向=%s 来源=%s 场景=%s",
        len(scored),
        rejected_relevance,
        rejected_score,
        len(selected),
        max(len(scored) - len(selected), 0),
        tag_counts,
        source_counts,
        use_case_counts,
    )
    return selected


def _policy_focus(item: RadarItem) -> str:
    return str((item.metrics or {}).get("policy_focus") or "").strip()


def select_policy_candidates(items):
    """按发布时间优先，同时保证 Amazon、进口新规、产品审核三类情报的代表性。"""
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


def _number(value) -> float:
    try:
        return max(float(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _normalized_level(value) -> str:
    level = str(value or "medium").strip().lower()
    return level if level in RISK_ORDER else "medium"


def _first_project_action(analysis: dict) -> str:
    ideas = analysis.get("startup_ideas") or []
    if not isinstance(ideas, list):
        return ""
    for value in ideas:
        text = " ".join(str(value or "").split()).strip()
        if text:
            return text
    return ""


def _final_project_utility_score(item: RadarItem) -> float:
    """最终推送排序：产品/业务价值为主，热度只占小部分，可执行性单独加权。"""
    analysis = item.analysis or {}
    metrics = item.metrics or {}
    local_selection = min(_number(metrics.get("selection_score")), 100)
    business = min(_number(analysis.get("business_score")), 100)
    trend = min(_number(item.trend_score), 100)

    action = _first_project_action(analysis)
    judgment = " ".join(str(analysis.get("summary") or "").split()).strip()
    categories = metrics.get("product_categories") or []
    actionability = 0.0
    if len(action) >= FINAL_MIN_ACTION_CHARS:
        actionability += 6.0
    if len(judgment) >= 40:
        actionability += 2.0
    if isinstance(categories, list) and categories:
        actionability += 2.0

    material_update_bonus = 3.0 if metrics.get("history_material_update") else 0.0
    score = (
        local_selection * 0.35
        + business * 0.45
        + trend * 0.10
        + actionability
        + material_update_bonus
    )
    return round(min(score, 100), 2)


def _passes_final_project_gate(item: RadarItem) -> bool:
    """DeepSeek 第二道 Gate：价值、内容完整度和可执行性都合格才进入飞书。"""
    analysis = item.analysis or {}
    item.metrics = dict(item.metrics or {})

    if _analysis_is_fallback(analysis):
        item.metrics["final_report_eligible"] = False
        item.metrics["final_gate_reason"] = "DeepSeek分析降级"
        return False

    score = _number(analysis.get("business_score"))
    opportunity = _normalized_level(analysis.get("opportunity"))
    threshold = FINAL_BUSINESS_SCORE.get(item.source, DEFAULT_FINAL_BUSINESS_SCORE)
    purpose = " ".join(str(analysis.get("purpose") or "").split()).strip()
    judgment = " ".join(str(analysis.get("summary") or "").split()).strip()
    action = _first_project_action(analysis)

    local_tags = set((item.metrics or {}).get("priority_tags") or [])
    local_product_path = bool((item.metrics or {}).get("physical_product_path"))
    if item.source in {"arxiv", "huggingface"}:
        source_path_valid = "跨境电商" in local_tags or local_product_path
    else:
        source_path_valid = True

    content_complete = (
        len(purpose) >= FINAL_MIN_PURPOSE_CHARS
        and len(judgment) >= FINAL_MIN_JUDGMENT_CHARS
        and len(action) >= FINAL_MIN_ACTION_CHARS
    )
    passed = (
        opportunity != "low"
        and score >= threshold
        and source_path_valid
        and content_complete
    )

    if opportunity == "low":
        reason = "DeepSeek机会等级低"
    elif score < threshold:
        reason = f"商业价值分不足：{score:.0f}<{threshold}"
    elif not source_path_valid:
        reason = "论文/模型缺少跨境或明确实体商品落地路径"
    elif len(purpose) < FINAL_MIN_PURPOSE_CHARS:
        reason = "项目用途信息不足"
    elif len(judgment) < FINAL_MIN_JUDGMENT_CHARS:
        reason = "价值判断信息不足"
    elif len(action) < FINAL_MIN_ACTION_CHARS:
        reason = "缺少可执行验证/开发动作"
    else:
        reason = "通过最终价值与可执行性门槛"

    utility_score = _final_project_utility_score(item) if passed else 0.0
    item.metrics["final_report_eligible"] = passed
    item.metrics["final_business_score"] = score
    item.metrics["final_opportunity"] = opportunity
    item.metrics["final_business_threshold"] = threshold
    item.metrics["final_actionable"] = len(action) >= FINAL_MIN_ACTION_CHARS
    item.metrics["final_gate_reason"] = reason
    item.metrics["final_utility_score"] = utility_score
    return passed


def apply_final_project_gate(projects):
    accepted = []
    rejected = []
    for item in projects or []:
        if _passes_final_project_gate(item):
            accepted.append(item)
        else:
            rejected.append(item)

    # DeepSeek 之后重新排序：不沿用采集阶段排名，让真正有用、可执行的项目排在最前面。
    accepted.sort(
        key=lambda item: (
            _number((item.metrics or {}).get("final_utility_score")),
            _number((item.analysis or {}).get("business_score")),
            _number((item.metrics or {}).get("selection_score")),
            _number(item.trend_score),
        ),
        reverse=True,
    )
    accepted = accepted[:MAX_REPORT_ITEMS]

    if rejected:
        logger.info(
            "DeepSeek最终裁决：分析=%s 推送=%s 淘汰=%s 淘汰项目=%s",
            len(projects or []),
            len(accepted),
            len(rejected),
            [
                f"{item.title}({(item.metrics or {}).get('final_gate_reason', '未通过')})"
                for item in rejected[:8]
            ],
        )
    else:
        logger.info(
            "DeepSeek最终裁决：分析=%s 推送=%s 淘汰=0 排名=%s",
            len(projects or []),
            len(accepted),
            [
                f"{item.title}:{(item.metrics or {}).get('final_utility_score', 0)}"
                for item in accepted[:5]
            ],
        )
    return accepted


def build_report(items):
    """兼容旧调用：本地筛选 + DeepSeek 分析 + 最终价值 Gate。"""
    candidates = select_project_candidates(items)
    analyze_digest(candidates, [])
    return apply_final_project_gate(candidates)


def filter_existing_items(db, items):
    """兼容旧调用；除 URL 外，同时过滤近期跨来源/改标题后的同一项目或政策。"""
    fresh, _ = filter_recently_reported(db, items)
    return fresh


def _format_age(item: RadarItem) -> str:
    hours = age_hours(item.to_dict())
    if hours is None:
        return "时间未知"
    if hours < 1:
        return "1小时内"
    if hours < 24:
        return f"{int(hours)}小时前"
    return f"{max(int(hours // 24), 1)}天前"


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
    return _first_project_action(analysis)


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
    """摘要只给决策导航，不复制正文中的完整动作/影响/实验字段。"""
    ordered_policies = sorted(compliance, key=_policy_priority, reverse=True)
    high_risk = [item for item in ordered_policies if item.risk_level == "high"]
    top_product = products[0] if products else None

    if high_risk:
        first = high_risk[0]
        identity = first.authority or first.source_name
        must_text = (
            f"先处理 {identity}｜{first.title}；具体适用范围、资料清单和执行动作见合规卡。"
        )
    elif ordered_policies:
        first = ordered_policies[0]
        must_text = "今日无新增高风险事项；完成最高影响合规变化的适用范围核对。"
    else:
        must_text = "今日无新增高影响合规事项，维持常规审核与准入资料检查。"

    if len(ordered_policies) > 1:
        second = ordered_policies[1]
        identity = second.authority or second.source_name
        focus_text = (
            f"关注 {identity}｜{second.title}；确认是否影响当前在售或拟售产品，细节见合规卡。"
        )
    elif ordered_policies:
        second = ordered_policies[0]
        identity = second.authority or second.source_name
        focus_text = f"继续跟踪 {identity}｜{second.title} 的适用范围与后续执行节点。"
    else:
        focus_text = "关注 Amazon、CBP、CPSC、FDA、FCC 后续新增要求。"

    if top_product:
        research_text = (
            f"优先验证 {top_product.title}；具体实验、成功条件和工程限制见产品机会卡。"
        )
    else:
        research_text = "今日暂无达到最终价值门槛的新产品机会。"

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
    return f"{base} 产品侧暂无达到最终价值门槛的新机会。"


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


def _legacy_product_group(product: ProductDecision) -> str:
    tags = set(product.tags or [])
    if product.cross_border:
        return "🎯 跨境电商直接相关项目"
    if "硬件开发" in tags or "实体商品机会" in tags:
        return "🧰 硬件与实体商品机会"
    if "技术前沿" in tags:
        return "🧠 技术前沿与开发基础设施"
    return "🧪 其他可产品化 AI 信号"


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

    grouped = {}
    for product in model.products:
        grouped.setdefault(_legacy_product_group(product), []).append(product)

    for title in (
        "🎯 跨境电商直接相关项目",
        "🧰 硬件与实体商品机会",
        "🧠 技术前沿与开发基础设施",
        "🧪 其他可产品化 AI 信号",
    ):
        group = grouped.get(title) or []
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
        new_items, project_history_duplicates = filter_recently_reported(db, radar_items)
        new_policies, policy_history_duplicates = filter_recently_reported(db, policy_items)
        logger.info(
            "历史去重完成：项目=%s 新项目=%s 跨天重复=%s 政策=%s 新政策=%s 跨天重复=%s",
            len(radar_items),
            len(new_items),
            project_history_duplicates,
            len(policy_items),
            len(new_policies),
            policy_history_duplicates,
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

    analysis_candidates = select_project_candidates(new_items)
    policy_report = select_policy_candidates(new_policies)
    analyze_digest(analysis_candidates, policy_report)

    report = apply_final_project_gate(analysis_candidates)
    final_rejected_count = len(analysis_candidates) - len(report)

    fallback_count = sum(
        1
        for item in policy_report + analysis_candidates
        if _analysis_is_fallback(item.analysis)
    )
    if fallback_count:
        errors.append(f"AI 分析降级 {fallback_count} 条")

    # 先构建卡片。若卡片本身构建失败，本轮不把条目标记为已完成，下一轮仍可重试。
    cards = None
    card_count = 0
    try:
        decision_model = build_decision_model(report, policy_report)
        cards = build_daily_cards(
            decision_model,
            max_projects=FEISHU_PROJECTS_PER_CARD,
        )
        card_count = len(cards)
    except Exception as exc:
        logger.exception("飞书日报构建失败：执行编号=%s", execution_id)
        errors.append(f"飞书日报构建失败：{exc}")

    saved_count = 0
    eligible_to_save = [
        item
        for item in policy_report + analysis_candidates
        if not _analysis_is_fallback(item.analysis)
    ]

    if cards is not None:
        try:
            # DeepSeek 淘汰的低价值项目也写入历史，防止下一天再次分析和消耗 Token；
            # 只有 report 集合会进入飞书。
            saved_records = save_batch(
                db,
                [item.to_dict() for item in policy_report + analysis_candidates],
            )
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
    else:
        logger.warning("卡片未构建成功，本轮跳过数据库完成标记：执行编号=%s", execution_id)

    db.close()

    feishu_sent = False
    if cards is not None:
        try:
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
            logger.exception("飞书日报发送失败：执行编号=%s", execution_id)
            errors.append(f"飞书日报发送失败：{exc}")

    status = "success" if not errors else "partial"
    duration = round(time.time() - started, 2)
    logger.info(
        "日报执行完成：执行编号=%s 状态=%s 耗时=%s秒 分析项目=%s 最终推送=%s AI淘汰=%s 政策=%s 保存=%s 飞书卡片=%s",
        execution_id,
        status,
        duration,
        len(analysis_candidates),
        len(report),
        final_rejected_count,
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
        "analyzed_projects": len(analysis_candidates),
        "filtered_projects": final_rejected_count,
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
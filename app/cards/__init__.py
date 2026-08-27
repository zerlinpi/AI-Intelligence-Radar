"""Structured decision models and Feishu card builders."""

from app.cards.models import (
    ActionItem,
    CardEnvelope,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)
from app.cards.priority_builders import (
    EMPTY_COMPLIANCE_TEXT,
    EMPTY_PRODUCT_TEXT,
    build_daily_cards as _build_daily_cards,
)
from app.core.logger import get_logger
from app.product_portfolio import compress_product_portfolio
from app.source_coverage import coverage_snapshot


logger = get_logger("飞书机会组合")

_EMPTY_COMPLIANCE_TEXT = EMPTY_COMPLIANCE_TEXT
_EMPTY_PRODUCT_TEXT = EMPTY_PRODUCT_TEXT

_SOURCE_PRIORITY = {
    "GitHub": 0,
    "Hugging Face": 1,
    "arXiv": 1,
    "Product Hunt": 2,
    "Hacker News": 2,
}


def _replace_text(node, old: str, new: str) -> None:
    """只替换飞书 payload 中精确命中的系统提示，不碰业务正文。"""
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str) and value == old:
                node[key] = new
            else:
                _replace_text(value, old, new)
        return
    if isinstance(node, list):
        for value in node:
            _replace_text(value, old, new)


def _prepend_coverage_note(model: ReportDecisionModel, note: str) -> None:
    note = str(note or "").strip()
    if not note:
        return
    judgment = str(getattr(model.summary, "judgment", "") or "").strip()
    if note in judgment:
        return
    model.summary.judgment = f"⚠️ {note} {judgment}".strip()


def _source_ordered_products(products):
    indexed = list(enumerate(products or []))
    indexed.sort(
        key=lambda row: (
            _SOURCE_PRIORITY.get(str(row[1].source_name or ""), 3),
            row[0],
        )
    )
    return [product for _, product in indexed]


def _refresh_source_metrics(model: ReportDecisionModel, metrics: dict) -> None:
    products = list(model.products or [])
    compliance = list(model.compliance or [])

    metrics["github_projects"] = sum(
        1 for item in products if item.source_name == "GitHub"
    )
    metrics["huggingface_projects"] = sum(
        1 for item in products if item.source_name == "Hugging Face"
    )
    metrics["arxiv_projects"] = sum(
        1 for item in products if item.source_name == "arXiv"
    )
    metrics["other_projects"] = sum(
        1
        for item in products
        if item.source_name not in {"GitHub", "Hugging Face", "arXiv"}
    )

    metrics["amazon_policies"] = sum(
        1 for item in compliance if item.focus == "Amazon政策与审核"
    )
    metrics["cross_border_rules"] = sum(
        1 for item in compliance if item.focus == "美国跨境新规"
    )
    metrics["product_compliance"] = sum(
        1 for item in compliance if item.focus == "产品合规审核"
    )


def _rewrite_summary_for_source_hierarchy(model: ReportDecisionModel, metrics: dict) -> None:
    if metrics.get("source_summary_applied"):
        return

    github_count = int(metrics.get("github_projects", 0) or 0)
    hf_count = int(metrics.get("huggingface_projects", 0) or 0)
    arxiv_count = int(metrics.get("arxiv_projects", 0) or 0)
    other_count = int(metrics.get("other_projects", 0) or 0)
    tech_count = hf_count + arxiv_count

    if github_count:
        source_judgment = f"项目侧以 GitHub 为主：{github_count} 个核心项目"
        if tech_count:
            source_judgment += f"；HF/arXiv {tech_count} 个技术补充"
        if other_count:
            source_judgment += f"；其他市场信号 {other_count} 个"
    else:
        source_judgment = "GitHub 本轮暂无通过最终价值门槛的核心项目"
        if tech_count:
            source_judgment += f"；HF/arXiv 仅保留 {tech_count} 个技术补充"
        if other_count:
            source_judgment += f"；其他市场信号 {other_count} 个"

    original = str(getattr(model.summary, "judgment", "") or "").strip()
    compliance_part = original.split("产品侧", 1)[0].strip() if "产品侧" in original else original
    compliance_part = compliance_part.rstrip("。；; ")
    model.summary.judgment = (
        f"{compliance_part}。{source_judgment}。"
        if compliance_part
        else f"{source_judgment}。"
    )

    top_github = next(
        (item for item in model.products if item.source_name == "GitHub"),
        None,
    )
    top_secondary = next(
        (
            item
            for item in model.products
            if item.source_name in {"Hugging Face", "arXiv"}
        ),
        None,
    )

    if top_github is not None:
        research_text = (
            f"优先研究 GitHub｜{top_github.title}；"
            "具体能力、增长证据和验证动作见 GitHub 核心项目卡。"
        )
    elif top_secondary is not None:
        research_text = (
            "本轮 GitHub 暂无通过最终价值门槛的核心项目；"
            f"技术补充先看 {top_secondary.title}。"
        )
    else:
        research_text = "本轮暂无达到最终价值门槛的新项目机会，不使用低质量候选补位。"

    for action in model.summary.actions:
        if str(action.label or "").strip() == "研究":
            action.text = research_text
            break

    metrics["source_summary_applied"] = 1


def _apply_product_portfolio(model: ReportDecisionModel) -> dict:
    """在最终飞书展示前压缩同质项目，并按来源层级组织最终日报。

    主流程已经完成相关性 Gate、DeepSeek 价值 Gate 和最终效用排序；这里不降低任何质量门槛。
    GitHub 作为项目主来源先进入最终组合，Hugging Face/arXiv 为技术补充，PH/HN 为其他信号。
    """
    metrics = dict(getattr(model.summary, "metrics", {}) or {})
    if metrics.get("portfolio_applied"):
        _refresh_source_metrics(model, metrics)
        _rewrite_summary_for_source_hierarchy(model, metrics)
        model.summary.metrics = metrics
        return {
            "input": metrics.get("portfolio_input", len(model.products)),
            "selected": len(model.products),
            "suppressed": metrics.get("portfolio_suppressed", 0),
        }

    # source order becomes the input order for the existing portfolio compressor. Because the compressor
    # keeps the first high-quality representative for a duplicated use case, GitHub wins equivalent
    # same-use-case ties without weakening any local/DeepSeek gate.
    ordered_products = _source_ordered_products(list(model.products or []))
    selected, stats = compress_product_portfolio(ordered_products)
    model.products = selected

    metrics["portfolio_applied"] = 1
    metrics["portfolio_input"] = int(stats.get("input", 0) or 0)
    metrics["portfolio_suppressed"] = int(stats.get("suppressed", 0) or 0)
    metrics["projects"] = len(selected)
    metrics["opportunities"] = sum(
        1
        for item in selected
        if str(item.opportunity or "").lower() == "high"
        or float(item.business_score or 0) >= 80
    )
    _refresh_source_metrics(model, metrics)
    _rewrite_summary_for_source_hierarchy(model, metrics)
    model.summary.metrics = metrics

    if stats.get("input"):
        logger.info(
            "最终机会组合：合格=%s 展示=%s 同场景压缩=%s GitHub=%s HF=%s arXiv=%s 其他=%s 场景=%s 方向=%s",
            stats.get("input"),
            stats.get("selected"),
            stats.get("suppressed"),
            metrics.get("github_projects", 0),
            metrics.get("huggingface_projects", 0),
            metrics.get("arxiv_projects", 0),
            metrics.get("other_projects", 0),
            stats.get("use_cases"),
            stats.get("lanes"),
        )
    return stats


def _rewrite_empty_state_cards(cards, model: ReportDecisionModel, coverage: dict) -> None:
    if not coverage.get("available") or coverage.get("complete"):
        return

    note = str(coverage.get("note") or "").strip()

    if not model.compliance and not coverage.get("policy_complete", True):
        replacement = (
            "⚠️ 本轮政策数据源覆盖不完整，当前不能据此判断“今日无新增合规变化”。"
            f"{note}"
        )
        for card in cards:
            if str(card.card_type).startswith("compliance"):
                _replace_text(card.payload, _EMPTY_COMPLIANCE_TEXT, replacement)
                card.fallback_text = card.fallback_text.replace(_EMPTY_COMPLIANCE_TEXT, replacement)

    if not model.products and not coverage.get("project_complete", True):
        replacement = (
            "⚠️ 本轮项目数据源覆盖不完整；在当前成功获取的来源中暂无通过最终价值门槛的新产品机会，"
            "但不能把缺失来源解释为“没有机会”。仍不使用低价值候选补位。"
        )
        for card in cards:
            if str(card.card_type).startswith("products"):
                _replace_text(card.payload, _EMPTY_PRODUCT_TEXT, replacement)
                card.fallback_text = card.fallback_text.replace(_EMPTY_PRODUCT_TEXT, replacement)


def build_daily_cards(
    model: ReportDecisionModel,
    max_projects=None,
):
    """生产卡片入口：GitHub主来源 + 合规清晰化 + 最终组合去同质化 + 无损分页。"""
    _apply_product_portfolio(model)

    coverage = coverage_snapshot()
    if coverage.get("available") and not coverage.get("complete"):
        _prepend_coverage_note(model, coverage.get("note") or "")

    if max_projects is None:
        cards = _build_daily_cards(model)
    else:
        cards = _build_daily_cards(model, max_projects=max_projects)

    _rewrite_empty_state_cards(cards, model, coverage)
    return cards


__all__ = [
    "ActionItem",
    "CardEnvelope",
    "ComplianceDecision",
    "DailySummary",
    "ProductDecision",
    "ReportDecisionModel",
    "build_daily_cards",
]

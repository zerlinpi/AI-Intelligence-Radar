"""Structured decision models and Feishu card builders."""

from app.cards.builders import build_daily_cards as _build_daily_cards
from app.cards.models import (
    ActionItem,
    CardEnvelope,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)
from app.core.logger import get_logger
from app.product_portfolio import compress_product_portfolio
from app.source_coverage import coverage_snapshot


logger = get_logger("飞书机会组合")

_EMPTY_COMPLIANCE_TEXT = "今日未发现新增的高影响 Amazon 政策、美国进口新规或产品审核要求。"
_EMPTY_PRODUCT_TEXT = "今日暂无通过最终价值门槛的新产品机会；不使用低价值候选补位。"


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


def _apply_product_portfolio(model: ReportDecisionModel) -> dict:
    """在最终飞书展示前压缩同质项目，不改变底层历史数据库。

    主流程已经完成相关性 Gate、DeepSeek 价值 Gate 和最终效用排序；本函数只处理
    “多条都合格但本质属于同一使用场景”的重复展示问题。
    """
    metrics = dict(getattr(model.summary, "metrics", {}) or {})
    if metrics.get("portfolio_applied"):
        return {
            "input": metrics.get("portfolio_input", len(model.products)),
            "selected": len(model.products),
            "suppressed": metrics.get("portfolio_suppressed", 0),
        }

    selected, stats = compress_product_portfolio(list(model.products or []))
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
    model.summary.metrics = metrics

    if stats.get("input"):
        logger.info(
            "最终机会组合：合格=%s 展示=%s 同场景压缩=%s 场景=%s 方向=%s",
            stats.get("input"),
            stats.get("selected"),
            stats.get("suppressed"),
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
    """生产卡片入口：最终组合去同质化 + 数据覆盖可信度 + 现有无损分页。

    组合压缩只在已经通过主流程最终价值 Gate 的项目之间进行，不会为了多样性引入低价值项目；
    采集健康信息完整时，再根据覆盖状态决定是否显示数据源告警。
    """
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

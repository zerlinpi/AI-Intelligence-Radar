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
from app.source_coverage import coverage_snapshot


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
    """生产卡片入口：在现有无损分页前注入本轮数据覆盖可信度。

    单独调用 Card Builder、单元测试或采集健康信息尚未收齐时保持原行为；
    只有生产一轮已经完成全部基础采集器后，才会显示覆盖告警。
    """
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

from __future__ import annotations

from typing import Any, Dict, Iterable

from app.cards import (
    ActionItem,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)


def _text(value: Any, default: str = "") -> str:
    value = default if value is None else value
    return str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "是"}


def _list(value: Any) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _actions(rows: Iterable[Any]) -> list[ActionItem]:
    actions = []
    for raw in rows:
        row = _dict(raw)
        label = _text(row.get("label"))
        text = _text(row.get("text"))
        if label and text:
            actions.append(ActionItem(label=label, text=text))
    return actions[:3]


def _compliance(rows: Iterable[Any]) -> list[ComplianceDecision]:
    decisions = []
    for raw in rows:
        row = _dict(raw)
        title = _text(row.get("title"))
        source_name = _text(row.get("source_name"))
        focus = _text(row.get("focus"))
        if not (title and source_name and focus):
            continue
        decisions.append(
            ComplianceDecision(
                focus=focus,
                title=title,
                source_name=source_name,
                authority=_text(row.get("authority")),
                kind=_text(row.get("kind")),
                age_text=_text(row.get("age_text")),
                url=_text(row.get("url")),
                risk_level=_text(row.get("risk_level"), "medium").lower(),
                impact_score=_number(row.get("impact_score"), 50),
                requirement=_text(row.get("requirement")),
                impact=_text(row.get("impact")),
                affected_products=_text(row.get("affected_products")),
                risk=_text(row.get("risk")),
                preparation=_text(row.get("preparation")),
                action=_text(row.get("action")),
            )
        )
    return decisions[:4]


def _products(rows: Iterable[Any]) -> list[ProductDecision]:
    decisions = []
    for raw in rows:
        row = _dict(raw)
        title = _text(row.get("title"))
        source_name = _text(row.get("source_name"))
        if not (title and source_name):
            continue
        tags = [_text(tag) for tag in _list(row.get("tags")) if _text(tag)]
        decisions.append(
            ProductDecision(
                title=title,
                source_name=source_name,
                age_text=_text(row.get("age_text")),
                url=_text(row.get("url")),
                trend_score=_number(row.get("trend_score"), 0),
                business_score=_number(row.get("business_score"), 0),
                opportunity=_text(row.get("opportunity"), "medium").lower(),
                tags=tags,
                description=_text(row.get("description")),
                growth_signal=_text(row.get("growth_signal")),
                judgment=_text(row.get("judgment")),
                direction=_text(row.get("direction")),
                cross_border=_boolean(row.get("cross_border")),
            )
        )
    return decisions[:10]


def report_model_from_dict(payload: Dict[str, Any]) -> ReportDecisionModel:
    """Convert a ChatGPT-authored daily intelligence payload into the existing card model.

    This module intentionally contains no Feishu layout logic. All presentation stays in
    app.cards so ChatGPT-authored reports render exactly through the production card path.
    """
    if not isinstance(payload, dict):
        raise TypeError("ChatGPT feed payload must be a JSON object")

    date_text = _text(payload.get("date_text"))
    judgment = _text(payload.get("judgment"))
    if not date_text:
        raise ValueError("ChatGPT feed is missing date_text")
    if not judgment:
        raise ValueError("ChatGPT feed is missing judgment")

    metrics = _dict(payload.get("metrics"))
    normalized_metrics = {}
    for key, value in metrics.items():
        try:
            normalized_metrics[_text(key)] = int(value)
        except (TypeError, ValueError):
            continue

    summary = DailySummary(
        date_text=date_text,
        judgment=judgment,
        actions=_actions(_list(payload.get("actions"))),
        metrics=normalized_metrics,
    )

    return ReportDecisionModel(
        summary=summary,
        compliance=_compliance(_list(payload.get("compliance"))),
        products=_products(_list(payload.get("products"))),
    )

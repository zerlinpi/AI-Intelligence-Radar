"""Feishu daily layout with GitHub as the primary project source.

This module reuses the proven payload/pagination primitives from ``builders`` and only
changes information architecture: business summary -> Amazon/import rules -> GitHub
core projects -> secondary technical signals. Business text is never truncated.
"""

from collections import defaultdict
from typing import List

from app.cards.builders import (
    _append_button,
    _append_policy_identity,
    _compliance_template,
    _element_text,
    _envelopes,
    _hr,
    _interactive_card,
    _md,
    _paginate_elements,
    _pair,
    _product_batch_elements,
    _project_elements,
    _text,
)
from app.cards.models import CardEnvelope, ReportDecisionModel
from app.cards.styles import (
    MAX_ACTIONS,
    PRODUCT_HEADER_TEMPLATE,
    RISK_LABELS,
    SUMMARY_HEADER_TEMPLATE,
)


EMPTY_COMPLIANCE_TEXT = (
    "**Amazon**：今日未发现新增高影响政策或审核变化。\n"
    "**美国跨境新规**：今日未发现新增高影响进口/清关规则。\n"
    "**产品合规**：今日未发现新增高影响 CPSC、FDA 或 FCC 要求。"
)
EMPTY_PRODUCT_TEXT = "今日暂无通过最终价值门槛的新产品机会；不使用低价值候选补位。"


def build_summary_cards(model: ReportDecisionModel) -> List[CardEnvelope]:
    summary = model.summary
    metrics = summary.metrics or {}

    compliance_line = (
        "🛒 Amazon **{amazon}**　·　🇺🇸 跨境新规 **{rules}**　·　"
        "🛡️ 产品合规 **{product_compliance}**　·　🔴 高风险 **{high_risk}**"
    ).format(
        amazon=metrics.get("amazon_policies", 0),
        rules=metrics.get("cross_border_rules", 0),
        product_compliance=metrics.get("product_compliance", 0),
        high_risk=metrics.get("high_risk", 0),
    )
    project_line = (
        "🐙 GitHub **{github}**（主）　·　🤗 HF **{hf}**　·　"
        "📚 arXiv **{arxiv}**　·　🌐 其他 **{other}**"
    ).format(
        github=metrics.get("github_projects", 0),
        hf=metrics.get("huggingface_projects", 0),
        arxiv=metrics.get("arxiv_projects", 0),
        other=metrics.get("other_projects", 0),
    )

    elements = [
        _pair("今日判断", _text(summary.judgment), "🧭"),
        _md(f"**经营汇总**\n{compliance_line}\n{project_line}"),
        _hr(),
        _md("**今天只看这 3 件事**"),
    ]

    number_labels = ("①", "②", "③")
    for index, action in enumerate(summary.actions[:MAX_ACTIONS]):
        elements.append(_pair(f"{number_labels[index]} {action.label}", action.text))

    return _envelopes(
        "summary",
        f"美国跨境经营雷达｜{summary.date_text}",
        elements,
        SUMMARY_HEADER_TEMPLATE,
    )


def _group_brief(group) -> str:
    highest = max(group, key=lambda item: item.impact_score)
    risk = RISK_LABELS.get(highest.risk_level, RISK_LABELS["medium"])
    authorities = "/".join(
        dict.fromkeys(
            _text(item.authority or item.source_name)
            for item in group
            if _text(item.authority or item.source_name)
        )
    )
    parts = [f"{len(group)}项", f"最高 {risk}", f"影响 {highest.impact_score:.0f}/100"]
    if authorities:
        parts.append(authorities)
    return " · ".join(parts)


def _append_amazon_policy(elements: list, decision, index: int) -> None:
    _append_policy_identity(elements, decision, index)
    elements.append(_md(f"**发生了什么**\n{_text(decision.requirement)}"))
    if decision.impact:
        elements.append(_pair("对卖家的影响", decision.impact, "📦"))
    if decision.action:
        elements.append(_pair("现在要做", decision.action, "✅"))
    _append_button(elements, "查看官方原文", decision.url)


def _append_import_rule(elements: list, decision, index: int) -> None:
    _append_policy_identity(elements, decision, index)
    elements.append(_md(f"**发生了什么**\n{_text(decision.requirement)}"))
    if decision.impact:
        elements.append(_pair("对进口/清关的影响", decision.impact, "🚚"))
    if decision.action:
        elements.append(_pair("现在要做", decision.action, "✅"))
    _append_button(elements, "查看官方原文", decision.url)


def _append_product_compliance(elements: list, decision, index: int) -> None:
    _append_policy_identity(elements, decision, index)
    elements.append(_md(f"**监管 / 审核要求**\n{_text(decision.requirement)}"))
    if decision.affected_products:
        elements.append(_pair("影响产品", decision.affected_products, "🎯"))
    if decision.risk:
        elements.append(_pair("不满足的风险", decision.risk, "⚠️"))
    if decision.preparation:
        elements.append(_pair("应准备资料", decision.preparation, "📋"))
    if decision.action:
        elements.append(_pair("现在要做", decision.action, "✅"))
    _append_button(elements, "查看官方原文", decision.url)


def build_compliance_cards(model: ReportDecisionModel) -> List[CardEnvelope]:
    decisions = list(model.compliance or [])
    date_text = model.summary.date_text
    template = _compliance_template(decisions)

    if not decisions:
        return _envelopes(
            "compliance",
            f"Amazon & 美国跨境规则｜{date_text}",
            [_md(EMPTY_COMPLIANCE_TEXT)],
            template,
        )

    grouped = defaultdict(list)
    for decision in decisions:
        grouped[decision.focus].append(decision)

    sections = (
        ("Amazon政策与审核", "🛒 Amazon 平台政策与审核", _append_amazon_policy),
        ("美国跨境新规", "🇺🇸 美国跨境进口新规", _append_import_rule),
        ("产品合规审核", "🛡️ 美国市场产品合规", _append_product_compliance),
    )

    elements = []
    display_index = 1
    for focus, title, renderer in sections:
        group = grouped.get(focus, [])
        if not group:
            continue
        if elements:
            elements.append(_hr())
        elements.append(_md(f"**{title} · {len(group)}项**"))
        elements.append(_pair("本组摘要", _group_brief(group), "📌"))

        for group_index, decision in enumerate(group):
            if group_index:
                elements.append(_hr())
            renderer(elements, decision, display_index)
            display_index += 1

    return _envelopes(
        "compliance",
        f"Amazon & 美国跨境规则｜{date_text}",
        elements,
        template,
    )


def _pages_to_envelopes(
    card_type: str,
    title: str,
    page_element_groups: list,
) -> List[CardEnvelope]:
    total = len(page_element_groups)
    envelopes = []
    for index, page in enumerate(page_element_groups, start=1):
        page_title = title if total == 1 else f"{title}｜{index}/{total}"
        page_type = card_type if total == 1 else f"{card_type}-{index}"
        fallback_lines = [page_title]
        fallback_lines.extend(
            text for text in (_element_text(element) for element in page) if text
        )
        envelopes.append(
            CardEnvelope(
                card_type=page_type,
                payload=_interactive_card(
                    page_title,
                    page,
                    template=PRODUCT_HEADER_TEMPLATE,
                ),
                fallback_text="\n".join(fallback_lines),
            )
        )
    return envelopes


def _build_github_cards(
    model: ReportDecisionModel,
    github_projects: list,
    max_projects: int,
) -> List[CardEnvelope]:
    date_text = model.summary.date_text
    title = f"GitHub 核心项目｜{date_text}"
    if not github_projects:
        return _envelopes(
            "products-github",
            title,
            [_md(EMPTY_PRODUCT_TEXT)],
            PRODUCT_HEADER_TEMPLATE,
        )

    preferred = max(int(max_projects or 1), 1)
    pages = []
    for offset in range(0, len(github_projects), preferred):
        batch = github_projects[offset: offset + preferred]
        elements = []
        if offset == 0:
            elements.append(
                _md(
                    "**主来源｜GitHub**\n"
                    "以下项目均已通过相关性、工程证据、DeepSeek 最终价值 Gate；"
                    "优先用于判断可复用软件能力、硬件原型和跨境业务工具。"
                )
            )
            elements.append(_hr())
        elements.extend(_product_batch_elements(batch, offset + 1))
        pages.extend(_paginate_elements(title, elements, PRODUCT_HEADER_TEMPLATE))

    return _pages_to_envelopes("products-github", title, pages)


def _secondary_batch_elements(batch, start_index: int) -> list:
    indexed = [(start_index + i, project) for i, project in enumerate(batch)]
    groups = (
        (
            "🤗 Hugging Face｜模型与端侧能力补充",
            [(index, project) for index, project in indexed if project.source_name == "Hugging Face"],
        ),
        (
            "📚 arXiv｜研究与技术方向补充",
            [(index, project) for index, project in indexed if project.source_name == "arXiv"],
        ),
        (
            "🌐 其他市场信号｜Product Hunt / Hacker News",
            [
                (index, project)
                for index, project in indexed
                if project.source_name not in {"Hugging Face", "arXiv"}
            ],
        ),
    )

    elements = []
    for title, group in groups:
        if not group:
            continue
        if elements:
            elements.append(_hr())
        elements.append(_md(f"**{title} · {len(group)}项**"))
        for group_index, (project_index, project) in enumerate(group):
            if group_index:
                elements.append(_hr())
            elements.extend(_project_elements(project, project_index))
    return elements


def _build_secondary_cards(
    model: ReportDecisionModel,
    projects: list,
    max_projects: int,
) -> List[CardEnvelope]:
    if not projects:
        return []

    date_text = model.summary.date_text
    title = f"技术补充信号｜HF / arXiv｜{date_text}"
    preferred = max(int(max_projects or 1), 1)
    pages = []
    for offset in range(0, len(projects), preferred):
        batch = projects[offset: offset + preferred]
        elements = []
        if offset == 0:
            elements.append(
                _md(
                    "**次要来源｜技术补充**\n"
                    "Hugging Face 与 arXiv 用于补充模型、端侧部署和研究方向；"
                    "Product Hunt / Hacker News 仅作为其他市场信号，不与 GitHub 核心项目平级。"
                )
            )
            elements.append(_hr())
        elements.extend(_secondary_batch_elements(batch, offset + 1))
        pages.extend(_paginate_elements(title, elements, PRODUCT_HEADER_TEMPLATE))

    return _pages_to_envelopes("products-secondary", title, pages)


def build_product_cards(
    model: ReportDecisionModel,
    max_projects: int = 5,
) -> List[CardEnvelope]:
    projects = list(model.products or [])
    github_projects = [project for project in projects if project.source_name == "GitHub"]
    secondary_projects = [project for project in projects if project.source_name != "GitHub"]

    cards = []
    cards.extend(_build_github_cards(model, github_projects, max_projects))
    cards.extend(_build_secondary_cards(model, secondary_projects, max_projects))
    return cards


def build_daily_cards(
    model: ReportDecisionModel,
    max_projects: int = 5,
) -> List[CardEnvelope]:
    """Production Feishu order: summary -> rules -> GitHub -> secondary signals."""
    cards = []
    cards.extend(build_summary_cards(model))
    cards.extend(build_compliance_cards(model))
    cards.extend(build_product_cards(model, max_projects=max_projects))
    return cards

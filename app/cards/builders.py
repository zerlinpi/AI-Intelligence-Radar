from collections import defaultdict
from typing import List

from app.cards.models import CardEnvelope, ReportDecisionModel
from app.cards.styles import (
    DAILY_HEADER_TEMPLATE,
    DECISION_BACKGROUND,
    DEFAULT_PROJECTS_PER_CARD,
    DISPLAY_LIMITS,
    FOCUS_TITLES,
    MAX_ACTIONS,
    OPPORTUNITY_LABELS,
    RISK_LABELS,
)
from app.cards.text import semantic_clip


def _md(content: str) -> dict:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": content},
    }


def _hr() -> dict:
    return {"tag": "hr"}


def _pair(label: str, body: str, icon: str = "") -> dict:
    left = f"{icon} **{label}**".strip()
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": DECISION_BACKGROUND,
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [_md(left)],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 4,
                "vertical_align": "top",
                "elements": [_md(body)],
            },
        ],
    }


def _interactive_card(title: str, elements: list, template: str = DAILY_HEADER_TEMPLATE) -> dict:
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {
                    "tag": "plain_text",
                    "content": semantic_clip(title, DISPLAY_LIMITS["header"]),
                },
            },
            "elements": elements,
        },
    }


def build_summary_card(model: ReportDecisionModel) -> CardEnvelope:
    summary = model.summary
    metrics = summary.metrics or {}
    judgment = semantic_clip(summary.judgment, DISPLAY_LIMITS["judgment"])
    elements = [
        _md(f"**今日判断**\n{judgment}"),
        _md(
            "合规 **{compliance}** · 高风险 **{high_risk}** · "
            "新项目 **{projects}** · 重点机会 **{opportunities}**".format(
                compliance=metrics.get("compliance", 0),
                high_risk=metrics.get("high_risk", 0),
                projects=metrics.get("projects", 0),
                opportunities=metrics.get("opportunities", 0),
            )
        ),
        _hr(),
    ]

    fallback_lines = [
        f"【美国跨境经营雷达｜{summary.date_text}】",
        f"今日判断：{judgment}",
    ]

    number_labels = ("①", "②", "③")
    for index, action in enumerate(summary.actions[:MAX_ACTIONS]):
        text = semantic_clip(action.text, DISPLAY_LIMITS["action"])
        label = f"{number_labels[index]} {action.label}"
        elements.append(_pair(label, text))
        fallback_lines.append(f"{label}：{text}")

    fallback_lines.append(
        "合规{compliance}｜高风险{high_risk}｜新项目{projects}｜重点机会{opportunities}".format(
            compliance=metrics.get("compliance", 0),
            high_risk=metrics.get("high_risk", 0),
            projects=metrics.get("projects", 0),
            opportunities=metrics.get("opportunities", 0),
        )
    )

    return CardEnvelope(
        card_type="summary",
        payload=_interactive_card(
            f"美国跨境经营雷达｜{summary.date_text}",
            elements,
        ),
        fallback_text="\n".join(fallback_lines),
    )


def _policy_header(decision, index: int) -> str:
    risk = RISK_LABELS.get(decision.risk_level, RISK_LABELS["medium"])
    meta = [part for part in (decision.authority, decision.kind, decision.age_text) if part]
    title = semantic_clip(decision.title, DISPLAY_LIMITS["policy_title"])
    return (
        f"**{index:02d}｜{decision.source_name}｜{title}**\n"
        f"{risk} · 影响 **{decision.impact_score:.0f}/100**"
        + (f" · {' · '.join(meta)}" if meta else "")
    )


def _append_standard_policy(elements: list, decision, index: int):
    elements.append(_md(_policy_header(decision, index)))
    if decision.focus == "美国跨境新规":
        first_label, second_label = "新规要点", "进口影响"
    else:
        first_label, second_label = "核心变化", "卖家影响"

    elements.append(
        _md(
            f"**{first_label}**\n"
            f"{semantic_clip(decision.requirement, DISPLAY_LIMITS['policy_requirement'])}"
        )
    )
    if decision.impact:
        elements.append(
            _md(
                f"**{second_label}**\n"
                f"{semantic_clip(decision.impact, DISPLAY_LIMITS['policy_impact'])}"
            )
        )
    action = semantic_clip(decision.action, DISPLAY_LIMITS["policy_action"])
    if action:
        content = f"✅ **下一步**：{action}"
        if decision.url:
            content += f"\n[查看官方原文 →]({decision.url})"
        elements.append(_md(content))


def _append_product_compliance(elements: list, decision, index: int):
    elements.append(_md(_policy_header(decision, index)))
    elements.append(
        _md(
            "**审核要求**\n"
            + semantic_clip(
                decision.requirement,
                DISPLAY_LIMITS["policy_requirement"],
            )
        )
    )
    elements.extend(
        [
            _pair(
                "影响产品",
                semantic_clip(
                    decision.affected_products,
                    DISPLAY_LIMITS["affected_products"],
                ),
                "🎯",
            ),
            _pair(
                "风险",
                semantic_clip(decision.risk, DISPLAY_LIMITS["risk"]),
                "⚠️",
            ),
            _pair(
                "准备资料",
                semantic_clip(
                    decision.preparation,
                    DISPLAY_LIMITS["preparation"],
                ),
                "📋",
            ),
        ]
    )
    action = semantic_clip(decision.action, DISPLAY_LIMITS["policy_action"])
    if action or decision.url:
        content = f"✅ **下一步**：{action}" if action else ""
        if decision.url:
            content += ("\n" if content else "") + f"[查看官方原文 →]({decision.url})"
        elements.append(_md(content))


def build_compliance_card(model: ReportDecisionModel) -> CardEnvelope:
    decisions = model.compliance
    date_text = model.summary.date_text
    elements = []
    fallback = [f"【美国合规雷达｜{date_text}】"]

    if not decisions:
        text = "今日未发现新增的高影响 Amazon 政策、美国进口新规或产品审核要求。"
        elements.append(_md(text))
        fallback.append(text)
        return CardEnvelope(
            card_type="compliance",
            payload=_interactive_card(f"美国合规雷达｜{date_text}", elements),
            fallback_text="\n".join(fallback),
        )

    groups = defaultdict(list)
    for decision in decisions:
        groups[decision.focus].append(decision)

    display_index = 1
    ordered_focus = ("Amazon政策与审核", "美国跨境新规", "产品合规审核")
    for focus in ordered_focus:
        group = groups.get(focus, [])
        if not group:
            continue

        if elements:
            elements.append(_hr())
        elements.append(_md(f"**{FOCUS_TITLES.get(focus, focus)}**"))
        fallback.append(FOCUS_TITLES.get(focus, focus))

        if focus == "产品合规审核":
            authorities = "/".join(
                dict.fromkeys(d.authority for d in group if d.authority)
            ) or "美国市场准入机构"
            highest = max(group, key=lambda d: d.impact_score)
            brief = (
                f"{len(group)} 条准入变化 · {authorities} · "
                f"最高 {RISK_LABELS.get(highest.risk_level, RISK_LABELS['medium'])}"
            )
            elements.append(_pair("审核简报", semantic_clip(brief, 72)))
            fallback.append(f"审核简报：{brief}")

        for decision in group:
            if focus == "产品合规审核":
                _append_product_compliance(elements, decision, display_index)
                fallback.extend(
                    [
                        f"{decision.source_name}｜{semantic_clip(decision.title, 32)}｜{RISK_LABELS.get(decision.risk_level, RISK_LABELS['medium'])}",
                        f"审核要求：{semantic_clip(decision.requirement, 72)}",
                        f"影响产品：{semantic_clip(decision.affected_products, 48)}",
                        f"风险：{semantic_clip(decision.risk, 56)}",
                        f"准备：{semantic_clip(decision.preparation, 64)}",
                        f"下一步：{semantic_clip(decision.action, 46)}",
                    ]
                )
            else:
                _append_standard_policy(elements, decision, display_index)
                fallback.extend(
                    [
                        f"{decision.source_name}｜{semantic_clip(decision.title, 32)}｜{RISK_LABELS.get(decision.risk_level, RISK_LABELS['medium'])}",
                        f"变化：{semantic_clip(decision.requirement, 72)}",
                        f"影响：{semantic_clip(decision.impact, 64)}",
                        f"下一步：{semantic_clip(decision.action, 46)}",
                    ]
                )
            display_index += 1

    return CardEnvelope(
        card_type="compliance",
        payload=_interactive_card(f"美国合规雷达｜{date_text}", elements),
        fallback_text="\n".join(line for line in fallback if line),
    )


def _project_block(project, index: int) -> dict:
    title = semantic_clip(project.title, DISPLAY_LIMITS["product_title"])
    opportunity = OPPORTUNITY_LABELS.get(project.opportunity, "中")
    tags = " ".join(f"`{tag}`" for tag in project.tags[:3])
    description = semantic_clip(
        project.description,
        DISPLAY_LIMITS["product_description"],
    )
    judgment = semantic_clip(
        project.judgment,
        DISPLAY_LIMITS["product_judgment"],
    )
    direction = semantic_clip(
        project.direction,
        DISPLAY_LIMITS["product_direction"],
    )

    lines = [
        f"**{index:02d}｜{title}**",
        (
            f"{project.source_name} · {project.age_text} · "
            f"🔥 {project.trend_score:.0f} · 💼 {project.business_score:.0f} {opportunity}"
        ),
    ]
    if tags:
        lines.append(tags)
    if description:
        lines.extend(["", description])
    if project.growth_signal:
        lines.append(f"**增长**：{project.growth_signal}")
    if judgment:
        lines.append(f"**判断**：{judgment}")
    if direction:
        lines.append(f"**方向**：{direction}")
    if project.url:
        lines.append(f"[查看项目 →]({project.url})")
    return _md("\n".join(lines))


def build_product_card(
    model: ReportDecisionModel,
    max_projects: int = DEFAULT_PROJECTS_PER_CARD,
) -> CardEnvelope:
    projects = list(model.products or [])
    selected = projects[: max(max_projects, 1)]
    omitted = max(len(projects) - len(selected), 0)
    date_text = model.summary.date_text
    elements = []
    fallback = [f"【产品机会雷达｜{date_text}】"]

    if not selected:
        text = "今日暂无达到展示优先级的新产品机会。"
        elements.append(_md(text))
        fallback.append(text)
    else:
        cross_border = [p for p in selected if p.cross_border]
        other = [p for p in selected if not p.cross_border]
        index = 1
        for title, group in (
            ("🎯 跨境电商直接相关", cross_border),
            ("🧪 其他可产品化信号", other),
        ):
            if not group:
                continue
            if elements:
                elements.append(_hr())
            elements.append(_md(f"**{title}**"))
            fallback.append(title)
            for project in group:
                elements.append(_project_block(project, index))
                fallback.extend(
                    [
                        f"{index:02d} {semantic_clip(project.title, 32)}｜🔥{project.trend_score:.0f}｜💼{project.business_score:.0f} {OPPORTUNITY_LABELS.get(project.opportunity, '中')}",
                        f"做什么：{semantic_clip(project.description, 72)}",
                        f"判断：{semantic_clip(project.judgment, 64)}",
                        f"方向：{semantic_clip(project.direction, 52)}",
                        f"链接：{project.url}" if project.url else "",
                    ]
                )
                index += 1
                if project is not group[-1]:
                    elements.append(_hr())

        if omitted:
            note = f"其余 {omitted} 个候选已入库，本卡只展示优先级最高的 {len(selected)} 个。"
            elements.extend([_hr(), _md(f"*{note}*")])
            fallback.append(note)

    return CardEnvelope(
        card_type="products",
        payload=_interactive_card(f"产品机会雷达｜{date_text}", elements),
        fallback_text="\n".join(line for line in fallback if line),
    )


def build_daily_cards(
    model: ReportDecisionModel,
    max_projects: int = DEFAULT_PROJECTS_PER_CARD,
) -> List[CardEnvelope]:
    """固定生成 3 张日报：决策摘要、合规雷达、产品机会。"""
    return [
        build_summary_card(model),
        build_compliance_card(model),
        build_product_card(model, max_projects=max_projects),
    ]

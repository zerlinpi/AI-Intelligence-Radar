from collections import defaultdict
from typing import List
from urllib.parse import urlparse

from app.cards.models import CardEnvelope, ReportDecisionModel
from app.cards.styles import (
    COMPLIANCE_HEADER_TEMPLATES,
    DECISION_BACKGROUND,
    DEFAULT_PROJECTS_PER_CARD,
    FOCUS_TITLES,
    MAX_ACTIONS,
    OPPORTUNITY_LABELS,
    PRODUCT_HEADER_TEMPLATE,
    RISK_LABELS,
    SUMMARY_HEADER_TEMPLATE,
)
from app.cards.text import clean_text, payload_bytes
from app.config import FEISHU_MAX_PAYLOAD_BYTES


# 不对业务正文设置字符上限。这里只给卡片 JSON 自身保留传输安全空间；
# 超过单卡预算时自动拆页/拆元素，正文必须逐字符守恒。
_PAYLOAD_RESERVE_BYTES = 768

OPPORTUNITY_BADGES = {
    "high": "🟢 高机会",
    "medium": "🟡 中机会",
    "low": "⚪ 观察",
}


def _text(value) -> str:
    return clean_text(value)


def _md(content: str) -> dict:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": str(content or "")},
    }


def _hr() -> dict:
    return {"tag": "hr"}


def _safe_http_url(value: str) -> str:
    """只允许标准 http/https 外链进入飞书 Button。"""
    url = _text(value)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _button(label: str, url: str, button_type: str = "default"):
    safe_url = _safe_http_url(url)
    if not safe_url:
        return None
    return {
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": _text(label)},
                "type": button_type,
                "url": safe_url,
            }
        ],
    }


def _append_button(
    elements: list,
    label: str,
    url: str,
    button_type: str = "default",
) -> None:
    button = _button(label, url, button_type)
    if button:
        elements.append(button)


def _pair_element(left: str, body: str) -> dict:
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


def _pair(label: str, body: str, icon: str = "") -> dict:
    left = f"{icon} **{label}**".strip()
    return _pair_element(left, _text(body))


def _interactive_card(
    title: str,
    elements: list,
    template: str = SUMMARY_HEADER_TEMPLATE,
) -> dict:
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {
                    "tag": "plain_text",
                    "content": _text(title),
                },
            },
            "elements": elements,
        },
    }


def _target_payload_bytes() -> int:
    configured = int(FEISHU_MAX_PAYLOAD_BYTES or 18 * 1024)
    return max(configured - _PAYLOAD_RESERVE_BYTES, 2048)


def _fits(title: str, elements: list, template: str) -> bool:
    return payload_bytes(_interactive_card(title, elements, template=template)) <= _target_payload_bytes()


def _preferred_break(text: str, hard_end: int) -> int:
    """在不丢字的前提下优先从自然语义边界拆分超长元素。"""
    if hard_end >= len(text):
        return len(text)

    floor = max(int(hard_end * 0.6), 1)
    window = text[floor:hard_end]
    best = -1
    for marker in ("\n", "。", "！", "？", "；", ";", "，", "、", " "):
        position = window.rfind(marker)
        if position > best:
            best = position
    if best >= 0:
        return floor + best + 1
    return hard_end


def _split_text_for_element(title: str, text: str, factory, template: str) -> list:
    """按实际 UTF-8 Payload 大小拆文本，不截断、不省略任何字符。"""
    value = str(text or "")
    if not value:
        return [factory("")]
    if _fits(title, [factory(value)], template):
        return [factory(value)]

    parts = []
    remaining = value
    while remaining:
        low, high = 1, len(remaining)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            if _fits(title, [factory(remaining[:middle])], template):
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        if best <= 0:
            best = 1

        cut = _preferred_break(remaining, best)
        if cut <= 0:
            cut = best
        parts.append(factory(remaining[:cut]))
        remaining = remaining[cut:]

    return parts


def _split_oversized_element(title: str, element: dict, template: str) -> list:
    if _fits(title, [element], template):
        return [element]

    tag = element.get("tag")
    if tag == "div":
        text = ((element.get("text") or {}).get("content") or "")
        return _split_text_for_element(title, text, _md, template)

    if tag == "column_set":
        columns = element.get("columns") or []
        if len(columns) >= 2:
            left_elements = columns[0].get("elements") or []
            right_elements = columns[1].get("elements") or []
            left = ""
            right = ""
            if left_elements:
                left = ((left_elements[0].get("text") or {}).get("content") or "")
            if right_elements:
                right = ((right_elements[0].get("text") or {}).get("content") or "")
            return _split_text_for_element(
                title,
                right,
                lambda chunk: _pair_element(left, chunk),
                template,
            )

    # action/hr 等固定小元素正常不会超预算；未知元素原样保留，由发送层做最终安全校验。
    return [element]


def _content_stream(element: dict) -> str:
    """提取需要守恒的正文；column_set 只取右侧正文，避免分页后重复标签干扰校验。"""
    tag = element.get("tag")
    if tag == "div":
        return str(((element.get("text") or {}).get("content") or ""))
    if tag == "column_set":
        columns = element.get("columns") or []
        if len(columns) >= 2:
            return "".join(
                _content_stream(child)
                for child in (columns[1].get("elements") or [])
            )
    return ""


def _paginate_elements(title: str, elements: list, template: str) -> list:
    """把完整元素流按真实 Payload 自动分页；分页前后业务正文必须逐字符守恒。"""
    expected_content = "".join(_content_stream(element) for element in elements)
    pages = []
    current = []
    reserve_title = f"{title}｜99/99"

    for raw_element in elements:
        for element in _split_oversized_element(reserve_title, raw_element, template):
            if current and not _fits(reserve_title, current + [element], template):
                pages.append(current)
                current = []
            current.append(element)

    if current or not pages:
        pages.append(current or [_md("暂无内容")])

    actual_content = "".join(
        _content_stream(element)
        for page in pages
        for element in page
    )
    if actual_content != expected_content:
        raise ValueError("飞书分页内容完整性校验失败：业务正文在分页过程中发生变化")

    return pages


def _element_text(element: dict) -> str:
    tag = element.get("tag")
    if tag == "hr":
        return "---"
    if tag == "div":
        return str(((element.get("text") or {}).get("content") or ""))
    if tag == "column_set":
        columns = element.get("columns") or []
        parts = []
        for column in columns:
            for child in column.get("elements") or []:
                text = _element_text(child)
                if text:
                    parts.append(text)
        return "：".join(parts)
    if tag == "action":
        parts = []
        for action in element.get("actions") or []:
            label = ((action.get("text") or {}).get("content") or "")
            url = action.get("url") or ""
            if label or url:
                parts.append(f"{label}：{url}".strip("："))
        return " | ".join(parts)
    return ""


def _envelopes(
    card_type: str,
    title: str,
    elements: list,
    template: str,
) -> List[CardEnvelope]:
    pages = _paginate_elements(title, elements, template)
    total = len(pages)
    envelopes = []
    for index, page in enumerate(pages, start=1):
        page_title = title if total == 1 else f"{title}｜{index}/{total}"
        page_type = card_type if total == 1 else f"{card_type}-{index}"
        fallback_lines = [page_title]
        fallback_lines.extend(
            text for text in (_element_text(element) for element in page) if text
        )
        envelopes.append(
            CardEnvelope(
                card_type=page_type,
                payload=_interactive_card(page_title, page, template=template),
                fallback_text="\n".join(fallback_lines),
            )
        )
    return envelopes


def build_summary_cards(model: ReportDecisionModel) -> List[CardEnvelope]:
    summary = model.summary
    metrics = summary.metrics or {}
    judgment = _text(summary.judgment)
    overview = (
        "🚨 合规 **{compliance}**　·　🔴 高风险 **{high_risk}**　·　"
        "💡 入选项目 **{projects}**　·　⭐ 重点机会 **{opportunities}**"
    ).format(
        compliance=metrics.get("compliance", 0),
        high_risk=metrics.get("high_risk", 0),
        projects=metrics.get("projects", 0),
        opportunities=metrics.get("opportunities", 0),
    )
    elements = [
        _pair("今日结论", judgment, "🧭"),
        _md(f"**今日状态**\n{overview}"),
        _hr(),
        _md("**执行优先级**"),
    ]

    number_labels = ("①", "②", "③")
    for index, action in enumerate(summary.actions[:MAX_ACTIONS]):
        label = f"{number_labels[index]} {action.label}"
        elements.append(_pair(label, action.text))

    return _envelopes(
        "summary",
        f"美国跨境经营雷达｜{summary.date_text}",
        elements,
        SUMMARY_HEADER_TEMPLATE,
    )


def build_summary_card(model: ReportDecisionModel) -> CardEnvelope:
    """兼容旧调用；生产路径使用 build_summary_cards 支持自动分页。"""
    return build_summary_cards(model)[0]


def _policy_meta(decision, index: int) -> str:
    risk = RISK_LABELS.get(decision.risk_level, RISK_LABELS["medium"])
    parts = [
        f"**{index:02d}｜{decision.source_name}**",
        risk,
        f"影响 **{decision.impact_score:.0f}/100**",
    ]
    for value in (decision.age_text, decision.authority, decision.kind):
        value = _text(value)
        if value and value not in {decision.source_name}:
            parts.append(value)
    return " · ".join(parts)


def _append_policy_identity(elements: list, decision, index: int) -> None:
    # 元信息与完整标题分行，防止长政策标题在移动端与风险/机构信息挤成一行。
    elements.append(_md(_policy_meta(decision, index)))
    elements.append(_md(f"**{_text(decision.title)}**"))


def _append_standard_policy(elements: list, decision, index: int):
    _append_policy_identity(elements, decision, index)
    if decision.focus == "美国跨境新规":
        first_label, second_label = "新规要点", "进口影响"
    else:
        first_label, second_label = "核心变化", "卖家影响"

    elements.append(_md(f"**{first_label}**\n{_text(decision.requirement)}"))
    if decision.impact:
        elements.append(_md(f"**{second_label}**\n{_text(decision.impact)}"))

    action = _text(decision.action)
    if action:
        elements.append(_pair("现在要做", action, "✅"))
    _append_button(elements, "查看官方原文", decision.url)


def _append_product_compliance(elements: list, decision, index: int):
    _append_policy_identity(elements, decision, index)
    elements.append(_md("**审核要求**\n" + _text(decision.requirement)))
    elements.extend(
        [
            _pair("影响产品", decision.affected_products, "🎯"),
            _pair("不满足的风险", decision.risk, "⚠️"),
            _pair("应准备资料", decision.preparation, "📋"),
        ]
    )
    action = _text(decision.action)
    if action:
        elements.append(_pair("现在要做", action, "✅"))
    _append_button(elements, "查看官方原文", decision.url)


def _compliance_template(decisions) -> str:
    if any(item.risk_level == "high" for item in decisions):
        return COMPLIANCE_HEADER_TEMPLATES["high"]
    if any(item.risk_level == "medium" for item in decisions):
        return COMPLIANCE_HEADER_TEMPLATES["medium"]
    return COMPLIANCE_HEADER_TEMPLATES["low"]


def build_compliance_cards(model: ReportDecisionModel) -> List[CardEnvelope]:
    decisions = model.compliance
    date_text = model.summary.date_text
    elements = []
    template = _compliance_template(decisions)

    if not decisions:
        elements.append(_md("今日未发现新增的高影响 Amazon 政策、美国进口新规或产品审核要求。"))
        return _envelopes(
            "compliance",
            f"美国合规雷达｜{date_text}",
            elements,
            template,
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
        group_title = FOCUS_TITLES.get(focus, focus)
        elements.append(_md(f"**{group_title} · {len(group)}项**"))

        if focus == "产品合规审核":
            authorities = "/".join(
                dict.fromkeys(d.authority for d in group if d.authority)
            ) or "美国市场准入机构"
            highest = max(group, key=lambda d: d.impact_score)
            brief = (
                f"{authorities} · 最高 "
                f"{RISK_LABELS.get(highest.risk_level, RISK_LABELS['medium'])} · "
                f"影响 {highest.impact_score:.0f}/100"
            )
            elements.append(_pair("本组判断", brief, "🛡️"))

        for group_index, decision in enumerate(group):
            if group_index:
                elements.append(_hr())
            if focus == "产品合规审核":
                _append_product_compliance(elements, decision, display_index)
            else:
                _append_standard_policy(elements, decision, display_index)
            display_index += 1

    return _envelopes(
        "compliance",
        f"美国合规雷达｜{date_text}",
        elements,
        template,
    )


def build_compliance_card(model: ReportDecisionModel) -> CardEnvelope:
    """兼容旧调用；生产路径使用 build_compliance_cards 支持自动分页。"""
    return build_compliance_cards(model)[0]


def _project_source_label(project) -> str:
    if project.source_name == "arXiv":
        return "📚 arXiv 研究论文"
    if project.source_name == "GitHub":
        return "GitHub 开源项目"
    if project.source_name == "Product Hunt":
        return "Product Hunt 新产品"
    if project.source_name == "Hugging Face":
        return "Hugging Face 模型/项目"
    if project.source_name == "Hacker News":
        return "Hacker News 产品信号"
    return project.source_name


def _project_button_label(project) -> str:
    if project.source_name == "arXiv":
        return "查看 arXiv 论文"
    if project.source_name == "GitHub":
        return "打开 GitHub 仓库"
    if project.source_name == "Hugging Face":
        return "查看模型/项目"
    if project.source_name == "Product Hunt":
        return "查看产品"
    if project.source_name == "Hacker News":
        return "查看讨论"
    return "查看项目"


def _direction_label(project, is_arxiv: bool) -> str:
    tags = set(project.tags or [])
    if is_arxiv:
        return "产品化验证"
    if "硬件开发" in tags or "实体商品机会" in tags:
        return "原型验证"
    if project.cross_border or "跨境电商" in tags:
        return "落地动作"
    if "技术前沿" in tags:
        return "开发验证"
    return "下一步"


def _opportunity_badge(project) -> str:
    return OPPORTUNITY_BADGES.get(project.opportunity, "🟡 中机会")


def _project_score_line(project, is_arxiv: bool) -> str:
    if is_arxiv:
        return f"💼 产品化价值 **{project.business_score:.0f}/100**"
    return (
        f"🔥 趋势 **{project.trend_score:.0f}/100**　·　"
        f"💼 价值 **{project.business_score:.0f}/100**"
    )


def _project_elements(project, index: int) -> list:
    title = _text(project.title)
    tags = " ".join(f"`{tag}`" for tag in project.tags)
    is_arxiv = project.source_name == "arXiv"

    # 第一行只负责“来源 + 时间 + 机会等级”，完整标题独占下一行。
    meta = (
        f"**{index:02d}｜{_project_source_label(project)}** · "
        f"{project.age_text} · {_opportunity_badge(project)}"
    )
    elements = [
        _md(meta),
        _md(f"**{title}**"),
        _md(_project_score_line(project, is_arxiv)),
    ]

    if tags:
        elements.append(_md(f"🏷️ {tags}"))

    description = _text(project.description)
    judgment = _text(project.judgment)
    direction = _text(project.direction)

    if description:
        description_label = "研究内容" if is_arxiv else "它能做什么"
        elements.append(_md(f"**{description_label}**\n{description}"))

    if is_arxiv:
        research_stage = _text(project.growth_signal) or "最新预印本研究 · 尚无产品市场验证"
        elements.append(_md(f"**研究阶段**\n{research_stage}"))
    elif project.growth_signal:
        elements.append(_md(f"📈 **增长证据**　{project.growth_signal}"))

    if judgment:
        elements.append(_pair("为什么值得看", judgment, "🧠"))
    if direction:
        elements.append(_pair(_direction_label(project, is_arxiv), direction, "🛠️"))

    _append_button(elements, _project_button_label(project), project.url)
    return elements


def _product_batch_elements(batch, start_index: int) -> list:
    """按战略价值分组；每个项目只进入优先级最高的一个板块，避免重复展示。"""
    indexed = [(start_index + i, p) for i, p in enumerate(batch)]

    cross_border = []
    hardware_physical = []
    frontier = []
    other = []

    for project_index, project in indexed:
        tags = set(project.tags or [])
        row = (project_index, project)
        if project.cross_border or "跨境电商" in tags:
            cross_border.append(row)
        elif "硬件开发" in tags or "实体商品机会" in tags:
            hardware_physical.append(row)
        elif "技术前沿" in tags:
            frontier.append(row)
        else:
            other.append(row)

    elements = []
    for title, group in (
        ("🎯 跨境电商直接相关", cross_border),
        ("🧰 硬件与实体商品机会", hardware_physical),
        ("🧠 技术前沿与开发基础设施", frontier),
        ("🧪 其他可产品化信号", other),
    ):
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


def build_product_cards(
    model: ReportDecisionModel,
    max_projects: int = DEFAULT_PROJECTS_PER_CARD,
) -> List[CardEnvelope]:
    projects = list(model.products or [])
    date_text = model.summary.date_text
    title = f"产品机会雷达｜{date_text}"

    if not projects:
        return _envelopes(
            "products",
            title,
            [_md("今日暂无通过最终价值门槛的新产品机会；不使用低价值候选补位。")],
            PRODUCT_HEADER_TEMPLATE,
        )

    preferred = max(int(max_projects or 1), 1)
    page_element_groups = []
    for offset in range(0, len(projects), preferred):
        batch = projects[offset: offset + preferred]
        batch_elements = _product_batch_elements(batch, offset + 1)
        # 每个“最多N项目”的逻辑批次仍会根据真实Payload继续细分，绝不删除后续项目。
        page_element_groups.extend(
            _paginate_elements(title, batch_elements, PRODUCT_HEADER_TEMPLATE)
        )

    total = len(page_element_groups)
    envelopes = []
    for index, page in enumerate(page_element_groups, start=1):
        page_title = title if total == 1 else f"{title}｜{index}/{total}"
        page_type = "products" if total == 1 else f"products-{index}"
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


def build_product_card(
    model: ReportDecisionModel,
    max_projects: int = DEFAULT_PROJECTS_PER_CARD,
) -> CardEnvelope:
    """兼容旧调用；生产路径使用 build_product_cards 支持完整分页。"""
    return build_product_cards(model, max_projects=max_projects)[0]


def build_daily_cards(
    model: ReportDecisionModel,
    max_projects: int = DEFAULT_PROJECTS_PER_CARD,
) -> List[CardEnvelope]:
    """生成三个逻辑板块；任一板块过长时自动拆成多张物理卡，正文不截断。"""
    cards = []
    cards.extend(build_summary_cards(model))
    cards.extend(build_compliance_cards(model))
    cards.extend(build_product_cards(model, max_projects=max_projects))
    return cards

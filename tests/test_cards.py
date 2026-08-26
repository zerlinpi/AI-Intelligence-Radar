from app.cards.builders import build_daily_cards
from app.cards.models import (
    ActionItem,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)
from app.cards.text import payload_bytes
from app.config import FEISHU_MAX_PAYLOAD_BYTES


def _model(project_count=7):
    summary = DailySummary(
        date_text="08月26日",
        judgment="发现 1 项高风险合规变化，先处理 CPSC 相关要求；产品侧优先研究 Listing 合规工具。",
        actions=[
            ActionItem("必须", "核对儿童产品 CPC/GCC 与 eFiling 字段。"),
            ActionItem("关注", "检查 Bluetooth/Wi-Fi 产品 FCC 授权资料。"),
            ActionItem("研究", "评估 Listing 生成与合规检查一体化产品方向。"),
            ActionItem("多余", "不应展示第四条"),
        ],
        metrics={
            "compliance": 3,
            "high_risk": 1,
            "projects": project_count,
            "opportunities": 2,
        },
    )

    compliance = [
        ComplianceDecision(
            focus="Amazon政策与审核",
            title="Testing and certification requirements",
            source_name="Amazon",
            authority="Amazon",
            age_text="1天前",
            url="https://example.com/amazon",
            risk_level="medium",
            impact_score=82,
            requirement="部分高风险产品需按平台要求完成测试和认证验证。",
            impact="未完成验证可能导致商品不可售或进入合规审核。",
            action="核对高风险 ASIN 的检测与认证资料。",
        ),
        ComplianceDecision(
            focus="产品合规审核",
            title="CPSC eFiling certificates",
            source_name="CPSC",
            authority="CPSC",
            kind="消费品安全",
            age_text="4小时前",
            url="https://example.com/cpsc",
            risk_level="high",
            impact_score=98,
            requirement="受监管消费品进口时需按要求申报合规证书数据。",
            affected_products="需要 CPC/GCC 的儿童产品及其他受监管消费品。",
            risk="证书或申报字段错误可能导致清关延误、整改或销售受阻。",
            preparation="测试报告、CPC/GCC 及 eFiling 所需申报字段。",
            action="先核对适用标准，再检查证书和申报字段。",
        ),
    ]

    products = []
    for index in range(project_count):
        products.append(
            ProductDecision(
                title=f"Project {index + 1}",
                source_name="GitHub",
                age_text="8小时前",
                url=f"https://example.com/project-{index + 1}",
                trend_score=90 - index,
                business_score=88 - index,
                opportunity="high" if index < 2 else "medium",
                tags=["跨境电商", "可产品化"] if index < 4 else ["可产品化"],
                description="帮助跨境卖家完成竞品分析、Listing 生成和多站点本地化。",
                growth_signal="⭐ 120 · Fork 8 · +40 星/天",
                judgment="需求明确，但通用工具竞争较强，垂直工作流更值得关注。",
                direction="开发 Listing 生成与合规检查一体化插件。",
                cross_border=index < 4,
            )
        )

    return ReportDecisionModel(
        summary=summary,
        compliance=compliance,
        products=products,
    )


def _serialized(cards):
    return "\n".join(str(card.payload) for card in cards)


def test_short_daily_report_keeps_three_logical_cards():
    cards = build_daily_cards(_model(project_count=2))
    assert [card.card_type for card in cards] == [
        "summary",
        "compliance",
        "products",
    ]


def test_summary_contains_today_judgment_and_only_three_actions():
    summary_card = build_daily_cards(_model(project_count=2))[0].payload
    blocks = [
        item
        for item in summary_card["card"]["elements"]
        if item.get("tag") == "column_set"
    ]

    # 今日判断 + ①必须 + ②关注 + ③研究。
    assert len(blocks) == 4
    assert all(block["background_style"] == "grey" for block in blocks)
    serialized = str(summary_card)
    assert "今日判断" in serialized
    assert "① 必须" in serialized
    assert "② 关注" in serialized
    assert "③ 研究" in serialized
    assert "不应展示第四条" not in serialized


def test_compliance_card_highlights_decision_fields_and_uses_buttons():
    compliance_card = build_daily_cards(_model(project_count=2))[1].payload
    blocks = [
        item
        for item in compliance_card["card"]["elements"]
        if item.get("tag") == "column_set"
    ]

    # Amazon 下一步 + 产品审核简报/影响产品/风险/准备资料/下一步。
    assert len(blocks) >= 6
    assert all(block["background_style"] == "grey" for block in blocks)
    serialized = str(compliance_card)
    assert "影响产品" in serialized
    assert "风险" in serialized
    assert "准备资料" in serialized
    assert "下一步" in serialized
    assert "查看官方原文" in serialized
    assert "button" in serialized


def test_product_card_separates_description_judgment_direction_and_uses_button():
    cards = build_daily_cards(_model(project_count=1))
    product_card = cards[-1].payload
    serialized = str(product_card)
    assert "做什么" in serialized
    assert "增长信号" in serialized
    assert "价值判断" in serialized
    assert "可借鉴方向" in serialized
    assert "查看项目" in serialized
    assert "button" in serialized


def test_all_projects_are_paginated_instead_of_omitted():
    cards = build_daily_cards(_model(project_count=9), max_projects=5)
    serialized = _serialized(cards)

    assert "Project 1" in serialized
    assert "Project 5" in serialized
    assert "Project 6" in serialized
    assert "Project 9" in serialized
    assert "其余 4 个候选已入库" not in serialized
    assert any(card.card_type.startswith("products-") for card in cards)


def test_long_business_copy_is_never_hard_truncated():
    model = _model(project_count=1)
    long_requirement = (
        "BEGIN-审核要求。"
        + "这是必须完整保留的美国市场产品审核说明，包含适用对象、条件、证书和执行要求。" * 500
        + "END-审核要求。"
    )
    long_risk = (
        "BEGIN-风险。"
        + "这是必须完整保留的风险说明，不能因为飞书展示预算直接裁掉。" * 500
        + "END-风险。"
    )
    long_description = (
        "BEGIN-产品描述。"
        + "这是必须完整保留的产品能力、工作方式和跨境电商应用场景。" * 500
        + "END-产品描述。"
    )

    compliance = model.compliance[-1]
    compliance.requirement = long_requirement
    compliance.risk = long_risk
    model.products[0].description = long_description

    cards = build_daily_cards(model, max_projects=5)
    serialized = _serialized(cards)

    assert "BEGIN-审核要求" in serialized
    assert "END-审核要求" in serialized
    assert "BEGIN-风险" in serialized
    assert "END-风险" in serialized
    assert "BEGIN-产品描述" in serialized
    assert "END-产品描述" in serialized
    assert len(cards) > 3


def test_every_generated_page_stays_inside_payload_budget():
    model = _model(project_count=10)
    model.products[0].description = "完整长文。" * 3000
    model.compliance[-1].preparation = "准备资料必须完整展示。" * 2000

    cards = build_daily_cards(model, max_projects=5)
    for card in cards:
        assert payload_bytes(card.payload) <= FEISHU_MAX_PAYLOAD_BYTES


def test_headers_use_distinct_visual_semantics():
    cards = build_daily_cards(_model(project_count=2))
    templates = {
        card.card_type: card.payload["card"]["header"]["template"]
        for card in cards
    }
    assert templates["summary"] == "turquoise"
    assert templates["compliance"] == "red"
    assert templates["products"] == "blue"

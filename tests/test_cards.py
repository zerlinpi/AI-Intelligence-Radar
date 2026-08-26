from app.cards.builders import build_daily_cards
from app.cards.models import (
    ActionItem,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)
from app.cards.text import payload_bytes


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


def test_daily_report_is_exactly_three_cards():
    cards = build_daily_cards(_model())
    assert [card.card_type for card in cards] == [
        "summary",
        "compliance",
        "products",
    ]


def test_summary_contains_only_three_actions_and_grey_blocks():
    summary_card = build_daily_cards(_model())[0].payload
    blocks = [
        item
        for item in summary_card["card"]["elements"]
        if item.get("tag") == "column_set"
    ]

    assert len(blocks) == 3
    assert all(block["background_style"] == "grey" for block in blocks)
    serialized = str(summary_card)
    assert "① 必须" in serialized
    assert "② 关注" in serialized
    assert "③ 研究" in serialized
    assert "不应展示第四条" not in serialized


def test_compliance_card_highlights_only_decision_fields():
    compliance_card = build_daily_cards(_model())[1].payload
    blocks = [
        item
        for item in compliance_card["card"]["elements"]
        if item.get("tag") == "column_set"
    ]

    # 产品审核：审核简报 + 影响产品 + 风险 + 准备资料。
    assert len(blocks) == 4
    assert all(block["background_style"] == "grey" for block in blocks)
    serialized = str(compliance_card)
    assert "影响产品" in serialized
    assert "风险" in serialized
    assert "准备资料" in serialized
    assert "查看官方原文" in serialized


def test_product_card_shows_at_most_five_projects():
    product_card = build_daily_cards(_model(project_count=9), max_projects=5)[2]
    serialized = str(product_card.payload)

    assert "Project 1" in serialized
    assert "Project 5" in serialized
    assert "Project 6" not in serialized
    assert "其余 4 个候选已入库" in serialized


def test_generated_cards_stay_under_18_kib_for_normal_report():
    cards = build_daily_cards(_model(project_count=10), max_projects=5)
    for card in cards:
        assert payload_bytes(card.payload) <= 18 * 1024


def test_all_daily_headers_are_turquoise():
    cards = build_daily_cards(_model())
    for card in cards:
        assert card.payload["card"]["header"]["template"] == "turquoise"

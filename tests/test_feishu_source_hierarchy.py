from app.cards import build_daily_cards
from app.cards.models import (
    ActionItem,
    ComplianceDecision,
    DailySummary,
    ProductDecision,
    ReportDecisionModel,
)


def _summary():
    return DailySummary(
        date_text="08月27日",
        judgment="今日有合规变化，但未发现新增高风险事项；先确认适用范围和资料完整性。产品侧优先研究某个项目。",
        actions=[
            ActionItem("必须", "先核对最高影响合规变化。"),
            ActionItem("关注", "关注其他美国市场要求。"),
            ActionItem("研究", "旧的研究动作会被来源层级刷新。"),
        ],
        metrics={"compliance": 2, "high_risk": 0, "projects": 4, "opportunities": 4},
    )


def _product(title, source, description, tags, *, cross_border=False):
    return ProductDecision(
        title=title,
        source_name=source,
        age_text="5小时前",
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        trend_score=82,
        business_score=86,
        opportunity="high",
        tags=tags,
        description=description,
        growth_signal="近期增长证据",
        judgment="已经通过最终价值门槛，值得进一步验证实际产品化价值。",
        direction="建立一个小范围原型并验证核心业务指标。",
        cross_border=cross_border,
    )


def _model():
    compliance = [
        ComplianceDecision(
            focus="Amazon政策与审核",
            title="Amazon seller verification update",
            source_name="Amazon",
            authority="Amazon",
            age_text="2小时前",
            url="https://example.com/amazon-policy",
            risk_level="medium",
            impact_score=82,
            requirement="Amazon 更新部分卖家审核资料要求。",
            impact="受影响卖家可能需要重新提交或补充验证资料。",
            action="核对账号通知并确认需要补充的文件。",
        ),
        ComplianceDecision(
            focus="美国跨境新规",
            title="CBP import filing update",
            source_name="美国海关 CBP",
            authority="CBP",
            age_text="3小时前",
            url="https://example.com/cbp-rule",
            risk_level="medium",
            impact_score=80,
            requirement="CBP 更新部分进口电子申报字段要求。",
            impact="进口商需要检查清关数据字段和申报流程。",
            action="核对当前报关模板与新增字段。",
        ),
    ]

    products = [
        _product(
            "GitHub Seller Workflow SDK",
            "GitHub",
            "Reusable Amazon seller inventory workflow SDK with API integration and automation components.",
            ["跨境电商", "可产品化"],
            cross_border=True,
        ),
        _product(
            "HF Edge Vision Model",
            "Hugging Face",
            "Quantized on-device object detection model for embedded cameras and low-power edge deployment.",
            ["技术前沿", "硬件开发", "实体商品机会", "商品·安防"],
        ),
        _product(
            "arXiv Sensor Fusion Research",
            "arXiv",
            "Research on low-power sensor fusion for wearable hardware with deployment measurements and prototype validation.",
            ["硬件开发", "实体商品机会", "商品·消费电子"],
        ),
        _product(
            "Product Hunt Pricing Tool",
            "Product Hunt",
            "Ecommerce pricing monitor for merchant repricing and competitor price tracking workflows.",
            ["跨境电商", "可产品化"],
            cross_border=True,
        ),
    ]

    return ReportDecisionModel(summary=_summary(), compliance=compliance, products=products)


def _serialized(card):
    return str(card.payload)


def test_daily_cards_use_github_as_primary_then_secondary_sources():
    cards = build_daily_cards(_model(), max_projects=5)
    types = [card.card_type for card in cards]

    assert types[0] == "summary"
    assert types[1] == "compliance"
    assert types[2].startswith("products-github")
    assert types[3].startswith("products-secondary")

    github_text = _serialized(cards[2])
    secondary_text = _serialized(cards[3])
    assert "GitHub 核心项目" in github_text
    assert "主来源｜GitHub" in github_text
    assert "GitHub Seller Workflow SDK" in github_text
    assert "HF Edge Vision Model" not in github_text

    assert "技术补充信号｜HF / arXiv" in secondary_text
    assert "次要来源｜技术补充" in secondary_text
    assert secondary_text.index("Hugging Face｜模型与端侧能力补充") < secondary_text.index("arXiv｜研究与技术方向补充")
    assert secondary_text.index("arXiv｜研究与技术方向补充") < secondary_text.index("其他市场信号｜Product Hunt / Hacker News")


def test_summary_aggregates_policy_and_source_counts_and_points_research_to_github():
    cards = build_daily_cards(_model(), max_projects=5)
    summary_text = _serialized(cards[0])

    assert "Amazon **1**" in summary_text
    assert "跨境新规 **1**" in summary_text
    assert "GitHub **1**（主）" in summary_text
    assert "HF **1**" in summary_text
    assert "arXiv **1**" in summary_text
    assert "其他 **1**" in summary_text
    assert "项目侧以 GitHub 为主" in summary_text
    assert "优先研究 GitHub｜GitHub Seller Workflow SDK" in summary_text


def test_amazon_and_import_rules_follow_fixed_business_reading_order():
    cards = build_daily_cards(_model(), max_projects=5)
    compliance_text = _serialized(cards[1])

    assert "Amazon & 美国跨境规则" in compliance_text
    assert "Amazon 平台政策与审核" in compliance_text
    assert "美国跨境进口新规" in compliance_text
    assert "本组摘要" in compliance_text
    assert "发生了什么" in compliance_text
    assert "对卖家的影响" in compliance_text
    assert "对进口/清关的影响" in compliance_text
    assert "现在要做" in compliance_text
    assert "查看官方原文" in compliance_text

    amazon_start = compliance_text.index("Amazon seller verification update")
    amazon_change = compliance_text.index("发生了什么", amazon_start)
    amazon_impact = compliance_text.index("对卖家的影响", amazon_start)
    amazon_action = compliance_text.index("现在要做", amazon_start)
    assert amazon_change < amazon_impact < amazon_action

    cbp_start = compliance_text.index("CBP import filing update")
    cbp_change = compliance_text.index("发生了什么", cbp_start)
    cbp_impact = compliance_text.index("对进口/清关的影响", cbp_start)
    cbp_action = compliance_text.index("现在要做", cbp_start)
    assert cbp_change < cbp_impact < cbp_action


def test_equivalent_same_use_case_prefers_github_over_secondary_source():
    github = _product(
        "GitHub Listing Engine",
        "GitHub",
        "Amazon seller product listing optimization and localization workflow automation for marketplace content teams.",
        ["跨境电商", "可产品化"],
        cross_border=True,
    )
    hf = _product(
        "HF Listing Model",
        "Hugging Face",
        "Amazon seller product listing optimization and localization workflow automation for marketplace content teams.",
        ["跨境电商", "可产品化"],
        cross_border=True,
    )
    model = ReportDecisionModel(
        summary=DailySummary(
            date_text="08月27日",
            judgment="今日未发现新增高风险合规事项。产品侧优先研究技术机会。",
            actions=[ActionItem("研究", "旧动作")],
            metrics={"compliance": 0, "high_risk": 0, "projects": 2, "opportunities": 2},
        ),
        compliance=[],
        # Intentionally put HF first to prove final source hierarchy is not inherited accidentally.
        products=[hf, github],
    )

    cards = build_daily_cards(model, max_projects=5)
    rendered = "\n".join(_serialized(card) for card in cards)

    assert "GitHub Listing Engine" in rendered
    assert "HF Listing Model" not in rendered
    assert model.summary.metrics["github_projects"] == 1
    assert model.summary.metrics["huggingface_projects"] == 0


def test_empty_compliance_state_explains_amazon_import_and_product_compliance_separately():
    model = ReportDecisionModel(
        summary=DailySummary(
            date_text="08月27日",
            judgment="今日未发现新增高风险合规事项。产品侧暂无达到最终价值门槛的新机会。",
            actions=[],
            metrics={"compliance": 0, "high_risk": 0, "projects": 0, "opportunities": 0},
        ),
        compliance=[],
        products=[],
    )

    cards = build_daily_cards(model, max_projects=5)
    compliance_text = _serialized(cards[1])

    assert "Amazon" in compliance_text
    assert "今日未发现新增高影响政策或审核变化" in compliance_text
    assert "美国跨境新规" in compliance_text
    assert "今日未发现新增高影响进口/清关规则" in compliance_text
    assert "产品合规" in compliance_text
    assert "CPSC、FDA 或 FCC" in compliance_text

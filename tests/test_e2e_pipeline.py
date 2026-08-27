from datetime import datetime, timezone

from app import pipeline
from app.cards import build_daily_cards
from app.models.radar_item import RadarItem


class MockCollector:
    def collect_safe(self):
        return [
            RadarItem(
                title="Test AI Project",
                source="test",
                url="https://example.com/project",
                description="A test project",
                metrics={"stars": 100},
            )
        ]


def test_collect_sources_converts_items(monkeypatch):
    monkeypatch.setattr(pipeline, "COLLECTORS", [MockCollector()])
    items = pipeline.collect_sources()
    assert len(items) == 1
    assert isinstance(items[0], RadarItem)
    assert items[0].title == "Test AI Project"


def test_decision_model_builds_three_feishu_cards():
    project = RadarItem(
        title="Seller AI Tool",
        source="github",
        url="https://example.com/project",
        description="AI tool for Amazon sellers",
        created_at=datetime.now(timezone.utc),
        metrics={
            "stars": 120,
            "forks": 8,
            "priority_tags": ["跨境电商", "可产品化"],
        },
    )
    project.trend_score = 80
    project.analysis = {
        "opportunity": "high",
        "business_score": 86,
        "purpose": "面向Amazon卖家的Listing运营工具，自动生成标题、卖点并优化多站点本地化内容。",
        "summary": "卖家需求直接，可嵌入日常上新流程并形成订阅SaaS。",
        "startup_ideas": ["做多站点Listing优化工具"],
    }

    amazon_policy = RadarItem(
        title="Testing and certification requirements",
        source="amazon_policy",
        url="https://example.com/amazon-policy",
        description="Amazon product testing requirement",
        category="policy",
        created_at=datetime.now(timezone.utc),
        metrics={
            "policy_source": "Amazon",
            "policy_authority": "Amazon",
            "policy_focus": "Amazon政策与审核",
            "policy_kind": "平台政策",
            "policy_score": 96,
        },
    )
    amazon_policy.analysis = {
        "opportunity": "high",
        "business_score": 94,
        "purpose": "部分高风险品类需通过Amazon认可的第三方检测、检验和认证流程。",
        "summary": "未按要求验证可能导致商品不可售或合规问题持续出现在Account Health。",
        "startup_ideas": ["提前准备测试样品并选择认可服务商"],
    }

    cpsc_policy = RadarItem(
        title="CPSC eFiling certificates",
        source="cpsc_compliance",
        url="https://example.com/cpsc",
        description="CPSC eFiling requirement",
        category="policy",
        created_at=datetime.now(timezone.utc),
        metrics={
            "policy_source": "美国消费品安全委员会 CPSC",
            "policy_authority": "CPSC",
            "policy_focus": "产品合规审核",
            "policy_kind": "消费品安全",
            "policy_score": 98,
        },
    )
    cpsc_policy.analysis = {
        "opportunity": "high",
        "business_score": 98,
        "purpose": "受监管消费品进口时需按要求电子申报CPC或GCC等合规证书数据。",
        "summary": "进口商需要确认商品是否落入证书和电子申报要求。",
        "affected_products": "儿童产品及其他需要CPC或GCC的受监管消费品",
        "risk": "证书或eFiling数据不完整可能导致清关延误、整改或销售受阻",
        "preparation": "第三方测试报告、CPC或GCC证书及eFiling所需申报字段",
        "startup_ideas": ["核对适用标准、测试报告及证书申报数据"],
    }

    model = pipeline.build_decision_model(
        [project],
        [amazon_policy, cpsc_policy],
    )
    cards = build_daily_cards(model)

    assert len(cards) == 3
    assert [card.card_type for card in cards] == [
        "summary",
        "compliance",
        "products",
    ]

    summary = str(cards[0].payload)
    compliance = str(cards[1].payload)
    products = str(cards[2].payload)

    assert "今日结论" in summary
    assert "今日状态" in summary
    assert "执行优先级" in summary
    assert "① 必须" in summary
    assert "② 关注" in summary
    assert "③ 研究" in summary

    assert "A｜Amazon 政策与审核" in compliance
    assert "C｜美国市场产品审核" in compliance
    assert "本组判断" in compliance
    assert "影响产品" in compliance
    assert "儿童产品" in compliance
    assert "不满足的风险" in compliance
    assert "清关延误" in compliance
    assert "应准备资料" in compliance
    assert "CPC" in compliance
    assert "现在要做" in compliance

    assert "跨境电商直接相关" in products
    assert "Seller AI Tool" in products
    assert "Listing" in products
    assert "为什么值得看" in products
    assert "落地动作" in products
    assert "打开 GitHub 仓库" in products

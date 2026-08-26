from datetime import datetime, timezone

from app import pipeline
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


def test_build_feishu_message_groups_compliance_and_projects():
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

    message = pipeline.build_feishu_message(
        [project],
        [amazon_policy, cpsc_policy],
    )

    assert "美国跨境经营雷达" in message
    assert "今日合规重点" in message
    assert "A｜Amazon 政策与审核" in message
    assert "C｜美国市场产品审核" in message
    assert "审核简报：" in message
    assert "重点影响产品：" in message
    assert "核心变化：" in message
    assert "审核要求：" in message
    assert "> 🎯 **影响产品：** **儿童产品及其他需要CPC或GCC的受监管消费品**" in message
    assert "> ⚠️ **风险：** **证书或eFiling数据不完整可能导致清关延误、整改或销售受阻**" in message
    assert "> 📋 **准备资料：** **第三方测试报告、CPC或GCC证书及eFiling所需申报字段**" in message
    assert "建议动作：" in message
    assert "跨境电商直接相关项目" in message
    assert "产品描述：" in message
    assert "增长信号：" in message
    assert "价值判断：" in message
    assert "可借鉴方向：" in message
    assert message.index("今日合规重点") < message.index("跨境电商直接相关项目")

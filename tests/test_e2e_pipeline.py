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


def test_build_feishu_message_groups_policy_and_cross_border_project():
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
        "purpose": "帮Amazon卖家优化商品Listing",
        "summary": "卖家场景直接，适合做订阅SaaS。",
        "startup_ideas": ["做Listing优化工具"],
    }

    policy = RadarItem(
        title="Update your shipping template settings",
        source="amazon_policy",
        url="https://example.com/policy",
        description="Amazon shipping policy update",
        category="policy",
        created_at=datetime.now(timezone.utc),
        metrics={
            "policy_source": "Amazon",
            "policy_kind": "平台政策",
            "policy_score": 90,
        },
    )
    policy.analysis = {
        "opportunity": "high",
        "business_score": 94,
        "purpose": "8月24日起调整自配送运费模板规则。",
        "summary": "仍用价格阶梯运费的卖家需要检查模板。",
        "startup_ideas": ["立即检查Shipping settings"],
    }

    message = pipeline.build_feishu_message([project], [policy])

    assert "跨境 AI 情报简报" in message
    assert "先处理｜政策与规则" in message
    assert "Amazon" in message
    assert "变化：" in message
    assert "影响：" in message
    assert "动作：" in message
    assert "优先看｜跨境电商机会" in message
    assert "Seller AI Tool" in message
    assert "做什么：" in message
    assert "为什么看：" in message
    assert "可做产品：" in message
    assert message.index("先处理｜政策与规则") < message.index("优先看｜跨境电商机会")

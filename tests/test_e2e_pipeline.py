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


def test_build_feishu_message():
    item = RadarItem(
        title="AI Test",
        source="github",
        url="https://example.com",
        description="description",
        metrics={
            "stars": 120,
            "forks": 8,
            "priority_tags": ["跨境电商", "可产品化"],
        },
    )
    item.trend_score = 80
    item.analysis = {
        "purpose": "帮助跨境卖家自动生成并优化商品Listing。",
        "opportunity": "high",
        "business_score": 86,
        "summary": "卖家需求明确，适合封装成独立SaaS工具。",
        "startup_ideas": ["做Listing优化与本地化工具"],
    }

    message = pipeline.build_feishu_message([item])

    assert "今日发现 1 个新项目" in message
    assert "优先：跨境电商相关 · 可产品化" in message
    assert "AI Test" in message
    assert "`GitHub`" in message
    assert "🔥 **80**" in message
    assert "💼 **86 · 高**" in message
    assert "🎯 跨境电商 · 可产品化" in message
    assert "🧩 **做什么：** 帮助跨境卖家自动生成并优化商品Listing。" in message
    assert "⭐ 120 · Fork 8" in message
    assert "🧠 **值得看：** 卖家需求明确，适合封装成独立SaaS工具。" in message
    assert "💡 **产品机会：** 做Listing优化与本地化工具" in message
    assert "[查看 →](https://example.com)" in message
    assert "排序额外优先跨境电商相关和可产品化项目" in message

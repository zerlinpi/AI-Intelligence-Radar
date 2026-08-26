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
        metrics={"stars": 120, "forks": 8},
    )
    item.trend_score = 80
    item.analysis = {
        "opportunity": "high",
        "business_score": 86,
        "summary": "这是一个值得关注的早期 AI 项目。",
        "startup_ideas": ["关注开发者工具方向"],
    }

    message = pipeline.build_feishu_message([item])

    assert "今日发现 1 个新项目" in message
    assert "AI Test" in message
    assert "`GitHub`" in message
    assert "🔥 **80**" in message
    assert "💼 **86 · 高**" in message
    assert "⭐ 120 · Fork 8" in message
    assert "这是一个值得关注的早期 AI 项目。" in message
    assert "关注开发者工具方向" in message
    assert "[查看 →](https://example.com)" in message
    assert "热度代表早期增长速度" in message

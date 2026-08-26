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
        source="test",
        url="https://example.com",
        description="description",
    )
    item.trend_score = 80
    item.analysis = {
        "opportunity": "high",
        "summary": "这是一个值得关注的早期 AI 项目。",
    }

    message = pipeline.build_feishu_message([item])

    assert "AI 新项目雷达" in message
    assert "AI Test" in message
    assert "商业机会：**高**" in message
    assert "新项目热度" in message
    assert "查看项目" in message

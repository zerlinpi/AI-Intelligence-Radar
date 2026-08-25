from app.models.radar_item import RadarItem


def test_radar_item_conversion():
    item = RadarItem(
        source="github",
        title="Test AI Project",
        url="https://example.com/project",
        description="AI project",
    )

    data = item.to_dict()

    assert data["source"] == "github"
    assert data["title"] == "Test AI Project"
    assert "metrics" in data


def test_radar_item_from_dict():
    item = RadarItem.from_dict({
        "source": "huggingface",
        "title": "Model",
        "metrics": {"downloads": 100},
    })

    assert item.source == "huggingface"
    assert item.metrics["downloads"] == 100

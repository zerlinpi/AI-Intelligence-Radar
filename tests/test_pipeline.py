from contextlib import contextmanager
from datetime import datetime, timezone

from app import pipeline
from app.models.radar_item import RadarItem
from app.pipeline import build_report


def test_build_report_returns_top_items():
    now = datetime.now(timezone.utc).isoformat()
    items = [
        {"title": "A", "created_at": now, "stars": 10},
        {"title": "B", "created_at": now, "stars": 20},
    ]

    result = build_report(items)

    assert isinstance(result, list)
    assert len(result) <= 10
    assert all(isinstance(item, RadarItem) for item in result)


def test_build_report_adds_analysis():
    now = datetime.now(timezone.utc).isoformat()
    items = [
        {
            "title": "Test Project",
            "url": "https://example.com",
            "created_at": now,
            "stars": 100,
        }
    ]

    result = build_report(items)

    assert len(result) == 1
    assert isinstance(result[0].analysis, dict)
    assert result[0].analysis


def test_cross_border_product_is_prioritized(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(
        pipeline,
        "analyze_items",
        lambda items: [
            {
                "purpose": "测试用途",
                "summary": "测试判断",
                "business_score": 80,
                "opportunity": "high",
                "startup_ideas": [],
            }
            for _ in items
        ],
    )

    items = [
        {
            "title": "General AI Research",
            "description": "A new neural network research project",
            "source": "github",
            "created_at": now,
            "stars": 100,
        },
        {
            "title": "Shopify Listing Copilot",
            "description": "AI tool for Amazon and Shopify product listings",
            "source": "github",
            "created_at": now,
            "stars": 20,
        },
    ]

    result = build_report(items)

    assert result[0].title == "Shopify Listing Copilot"
    assert result[0].metrics["priority_tags"] == ["跨境电商", "可产品化"]
    assert result[0].metrics["priority_score"] == 30


def test_run_daily_radar_skips_when_another_execution_is_running(monkeypatch):
    @contextmanager
    def locked():
        yield False

    monkeypatch.setattr(pipeline, "execution_lock", locked)

    result = pipeline.run_daily_radar()

    assert result["skipped"] is True
    assert result["reason"] == "已有任务正在运行"
    assert result["items"] == []

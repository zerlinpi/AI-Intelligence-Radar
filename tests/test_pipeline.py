from app.pipeline import build_report


def test_build_report_returns_top_items():
    items = [
        {"title": "A", "trend_score": 10},
        {"title": "B", "trend_score": 20},
    ]

    result = build_report(items)

    assert isinstance(result, list)
    assert len(result) <= 10


def test_build_report_adds_analysis_fallback():
    items = [
        {"title": "Test Project", "url": "https://example.com", "stars": 100}
    ]

    result = build_report(items)

    assert len(result) == 1
    assert "analysis" in result[0]

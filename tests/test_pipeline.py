from app.pipeline import build_report


def test_build_report_returns_top_items():
    items = [
        {"title": "A", "trend": 1},
        {"title": "B", "trend": 2},
    ]

    result = build_report(items)

    assert isinstance(result, list)
    assert len(result) <= 10

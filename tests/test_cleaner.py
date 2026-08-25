from app.cleaner import normalize_items


def test_normalize_items_removes_invalid_and_duplicates():
    items = [
        {"title": "Project A", "url": "https://example.com/a"},
        {"title": "Project A duplicate", "url": "https://example.com/a"},
        {"title": ""},
        None,
    ]

    result = normalize_items(items)

    assert len(result) == 1
    assert result[0]["source"] == "unknown"
    assert "stars" in result[0]

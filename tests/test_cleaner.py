from app.cleaner import normalize_items


def test_normalize_items_removes_invalid_and_duplicates():
    items = [
        {
            "title": "Project A",
            "url": "https://example.com/a",
            "stars": 12,
        },
        {"title": "Project A duplicate", "url": "https://example.com/a"},
        {"title": ""},
        None,
    ]

    result = normalize_items(items)

    assert len(result) == 1
    assert result[0]["source"] == "unknown"
    assert result[0]["stars"] == 12
    assert result[0]["metrics"]["stars"] == 12


def test_cross_source_same_project_is_merged_once():
    items = [
        {
            "source": "github",
            "title": "acme/seller-copilot",
            "url": "https://github.com/acme/seller-copilot",
            "description": "Amazon seller listing automation SDK with API and workflow support",
            "metrics": {"stars": 120, "language": "Python"},
        },
        {
            "source": "hackernews",
            "title": "Show HN: Seller Copilot",
            "url": "https://news.ycombinator.com/item?id=1",
            "description": "Seller Copilot is an Amazon seller listing automation SDK with API and workflow support",
            "metrics": {"upvotes": 80, "comments": 15},
        },
    ]

    result = normalize_items(items)

    assert len(result) == 1
    assert result[0]["source"] == "github"
    assert result[0]["metrics"]["stars"] == 120
    assert result[0]["metrics"]["upvotes"] == 80
    assert set(result[0]["metrics"]["also_seen_on"]) == {"github", "hackernews"}


def test_similar_generic_titles_with_different_descriptions_are_not_merged():
    items = [
        {
            "source": "github",
            "title": "AI Seller Assistant",
            "url": "https://github.com/acme/a",
            "description": "Amazon listing optimization and keyword research",
        },
        {
            "source": "producthunt",
            "title": "AI Seller Assistant Pro",
            "url": "https://example.com/b",
            "description": "Warehouse robotics control software for industrial picking",
        },
    ]

    result = normalize_items(items)

    assert len(result) == 2

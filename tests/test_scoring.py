from app.scoring import (
    calculate_priority_score,
    calculate_score,
    priority_tags,
)


def test_score_range():
    score = calculate_score({
        "stars": 10000,
        "forks": 1000,
        "comments": 500,
        "downloads": 100000,
        "upvotes": 500,
    })

    assert 0 <= score <= 100


def test_more_popular_item_scores_higher():
    low = calculate_score({"stars": 10})
    high = calculate_score({"stars": 10000})

    assert high > low


def test_cross_border_ecommerce_project_gets_priority():
    item = {
        "title": "AI Shopify Listing Copilot",
        "description": "Automates Amazon and Shopify product listing optimization",
        "source": "github",
    }

    assert priority_tags(item) == ["跨境电商", "可产品化"]
    assert calculate_priority_score(item) == 30


def test_research_only_project_has_no_business_priority():
    item = {
        "title": "Transformer Attention Research",
        "description": "A theoretical study of neural network attention",
        "source": "arxiv",
    }

    assert priority_tags(item) == []
    assert calculate_priority_score(item) == 0

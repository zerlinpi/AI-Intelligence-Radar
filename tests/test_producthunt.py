from datetime import datetime, timedelta, timezone

from app.sources import producthunt


class MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_producthunt_missing_token_returns_empty(monkeypatch):
    monkeypatch.delenv("PRODUCT_HUNT_TOKEN", raising=False)

    assert producthunt.ProductHuntCollector().collect() == []


def test_producthunt_collects_recent_relevant_ai_products(monkeypatch):
    monkeypatch.setenv("PRODUCT_HUNT_TOKEN", "test-token")

    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")

    payload = {
        "data": {
            "posts": {
                "edges": [
                    {
                        "node": {
                            "id": "1",
                            "name": "Fresh Amazon Seller AI",
                            "tagline": "An AI agent for Amazon sellers",
                            "description": "Automates product listing optimization and seller research workflows.",
                            "url": "https://www.producthunt.com/posts/fresh-amazon-seller-ai",
                            "website": "https://example.com/fresh-amazon-seller-ai",
                            "votesCount": 120,
                            "commentsCount": 20,
                            "createdAt": recent,
                            "topics": {"edges": []},
                        }
                    },
                    {
                        "node": {
                            "id": "2",
                            "name": "Old AI Product",
                            "tagline": "AI assistant",
                            "description": "",
                            "url": "https://www.producthunt.com/posts/old-ai-product",
                            "website": "https://example.com/old-ai-product",
                            "votesCount": 500,
                            "commentsCount": 50,
                            "createdAt": old,
                            "topics": {"edges": []},
                        }
                    },
                    {
                        "node": {
                            "id": "3",
                            "name": "Fresh Calendar",
                            "tagline": "A simple calendar",
                            "description": "",
                            "url": "https://www.producthunt.com/posts/fresh-calendar",
                            "website": "https://example.com/fresh-calendar",
                            "votesCount": 300,
                            "commentsCount": 40,
                            "createdAt": recent,
                            "topics": {"edges": []},
                        }
                    },
                ]
            }
        }
    }

    monkeypatch.setattr(
        producthunt.requests,
        "post",
        lambda *args, **kwargs: MockResponse(payload),
    )

    result = producthunt.ProductHuntCollector().collect(limit=10)

    assert len(result) == 1
    assert result[0]["title"] == "Fresh Amazon Seller AI"
    assert result[0]["upvotes"] == 120
    assert result[0]["metrics"]["comments"] == 20
    assert result[0]["metrics"]["momentum"] > 0
    assert result[0]["metrics"]["report_eligible"] is True
    assert "Amazon sellers" in result[0]["description"]
    assert "product listing optimization" in result[0]["description"]

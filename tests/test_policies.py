from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.sources import policies


def _entry(title, hours_ago, link="https://example.com/policy", summary="policy update effective soon"):
    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        description=summary,
        published_parsed=created.timetuple(),
        updated_parsed=None,
    )


def test_policy_collector_keeps_recent_relevant_items(monkeypatch):
    feed = SimpleNamespace(
        entries=[
            _entry(
                "New seller shipping requirement - Amazon Seller Forums",
                12,
                "https://example.com/new",
                "Starting August 24 sellers must update shipping requirements.",
            ),
            _entry(
                "Old seller policy update - Amazon Seller Forums",
                24 * 45,
                "https://example.com/old",
                "Policy requirement update.",
            ),
            _entry(
                "General marketing story",
                8,
                "https://example.com/story",
                "A seller success story without any rule changes.",
            ),
        ]
    )

    monkeypatch.setattr(policies, "POLICY_QUERIES", (policies.POLICY_QUERIES[0],))
    monkeypatch.setattr(policies, "_fetch_feed", lambda _query: feed)

    result = policies.PolicyCollector().collect(limit=5)

    assert len(result) == 1
    assert result[0]["category"] == "policy"
    assert result[0]["metrics"]["policy_source"] == "Amazon"
    assert "shipping requirement" in result[0]["title"].lower()


def test_policy_title_cleanup():
    assert policies._clean_title(
        "Answers to your product title update questions - Amazon Seller Forums"
    ) == "Answers to your product title update questions"

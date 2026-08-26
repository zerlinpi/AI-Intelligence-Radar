from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.sources import policies


def _entry(title, days_ago, link, summary):
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        description=summary,
        published_parsed=created.timetuple(),
        updated_parsed=None,
    )


def test_report_window_rejects_old_item_even_when_search_lookback_allows_it():
    now = datetime.now(timezone.utc)
    assert policies._within_report_window(now - timedelta(days=10), now, 21) is True
    assert policies._within_report_window(now - timedelta(days=30), now, 21) is False


def test_amazon_collector_does_not_push_older_baseline_as_today_news(monkeypatch):
    amazon_source = policies.POLICY_QUERIES[0]
    assert amazon_source["lookback_days"] > amazon_source["report_days"]

    feed = SimpleNamespace(
        entries=[
            _entry(
                "New product compliance requirement - Amazon Seller Forums",
                2,
                "https://example.com/recent",
                "Starting now sellers must submit product compliance documentation before listing.",
            ),
            _entry(
                "Older product compliance requirement - Amazon Seller Forums",
                35,
                "https://example.com/old-baseline",
                "Sellers must submit product compliance documentation before listing.",
            ),
        ]
    )

    monkeypatch.setattr(policies, "POLICY_QUERIES", (amazon_source,))
    monkeypatch.setattr(policies, "_fetch_feed", lambda _query: feed)

    result = policies.PolicyCollector().collect(limit=10)
    urls = {item["url"] for item in result}

    assert "https://example.com/recent" in urls
    assert "https://example.com/old-baseline" not in urls
    assert all(item["metrics"]["report_days"] == 21 for item in result)

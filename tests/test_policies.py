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
                "New seller compliance requirement - Amazon Seller Forums",
                12,
                "https://example.com/new",
                "Starting August 24 sellers must submit product compliance documentation.",
            ),
            _entry(
                "Old seller policy update - Amazon Seller Forums",
                24 * 90,
                "https://example.com/old",
                "Policy requirement update.",
            ),
            _entry(
                "General marketing story",
                8,
                "https://example.com/story",
                "A seller success story without any meaningful regulatory change.",
            ),
        ]
    )

    monkeypatch.setattr(policies, "POLICY_QUERIES", (policies.POLICY_QUERIES[0],))
    monkeypatch.setattr(policies, "_fetch_feed", lambda _query: feed)

    result = policies.PolicyCollector().collect(limit=5)

    assert len(result) == 1
    assert result[0]["category"] == "policy"
    assert result[0]["metrics"]["policy_source"] == "Amazon"
    assert result[0]["metrics"]["policy_focus"] == "Amazon政策与审核"
    assert result[0]["metrics"]["policy_authority"] == "Amazon"
    assert "compliance requirement" in result[0]["title"].lower()


def test_cpsc_policy_is_tagged_as_product_compliance(monkeypatch):
    cpsc_source = next(
        source
        for source in policies.POLICY_QUERIES
        if source["source"] == "cpsc_compliance"
    )
    feed = SimpleNamespace(
        entries=[
            _entry(
                "eFiling certificate requirement for consumer products | CPSC.gov",
                24,
                "https://example.com/cpsc",
                "Importers must eFile certificates of compliance through CBP beginning July 8, 2026.",
            )
        ]
    )

    monkeypatch.setattr(policies, "POLICY_QUERIES", (cpsc_source,))
    monkeypatch.setattr(policies, "_fetch_feed", lambda _query: feed)

    result = policies.PolicyCollector().collect(limit=5)

    assert len(result) == 1
    assert result[0]["source"] == "cpsc_compliance"
    assert result[0]["metrics"]["policy_focus"] == "产品合规审核"
    assert result[0]["metrics"]["policy_authority"] == "CPSC"


def test_policy_title_cleanup():
    assert policies._clean_title(
        "Answers to your product title update questions - Amazon Seller Forums"
    ) == "Answers to your product title update questions"

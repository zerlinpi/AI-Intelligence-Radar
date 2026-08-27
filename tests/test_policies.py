from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests

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


def test_policy_source_health_marks_failed_authority(monkeypatch):
    amazon_source = next(
        source for source in policies.POLICY_QUERIES
        if source["authority"] == "Amazon"
    )
    cbp_source = next(
        source for source in policies.POLICY_QUERIES
        if source["authority"] == "CBP"
    )
    cpsc_source = next(
        source for source in policies.POLICY_QUERIES
        if source["authority"] == "CPSC"
    )
    monkeypatch.setattr(
        policies,
        "POLICY_QUERIES",
        (amazon_source, cbp_source, cpsc_source),
    )

    def fake_fetch(query):
        if "site:cbp.gov" in query:
            raise requests.ConnectionError("cbp unavailable")
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(policies, "_fetch_feed", fake_fetch)
    collector = policies.PolicyCollector()

    assert collector.collect_safe(limit=5) == []
    policy_health = collector.get_policy_source_health()
    overall = collector.get_last_health()

    assert policy_health["complete"] is False
    assert policy_health["authorities_total"] == 3
    assert policy_health["authorities_success"] == 2
    assert policy_health["failed_authorities"] == ["CBP"]
    assert policy_health["authorities"]["CBP"]["success"] is False
    assert overall["success"] is False
    assert "CBP" in overall["error"]


def test_redundant_amazon_query_failure_is_degraded_not_full_failure(monkeypatch):
    amazon_sources = tuple(
        source for source in policies.POLICY_QUERIES
        if source["authority"] == "Amazon"
    )
    assert len(amazon_sources) >= 2
    monkeypatch.setattr(policies, "POLICY_QUERIES", amazon_sources)

    def fake_fetch(query):
        if "sellercentral.amazon.com" in query:
            raise requests.ConnectionError("seller forums unavailable")
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(policies, "_fetch_feed", fake_fetch)
    collector = policies.PolicyCollector()

    assert collector.collect_safe(limit=5) == []
    policy_health = collector.get_policy_source_health()
    overall = collector.get_last_health()

    assert policy_health["complete"] is True
    assert policy_health["query_complete"] is False
    assert policy_health["failed_authorities"] == []
    assert policy_health["degraded_authorities"] == ["Amazon"]
    assert policy_health["authorities"]["Amazon"]["queries_success"] == 1
    assert overall["success"] is True


def test_policy_title_cleanup():
    assert policies._clean_title(
        "Answers to your product title update questions - Amazon Seller Forums"
    ) == "Answers to your product title update questions"

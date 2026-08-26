from datetime import datetime, timezone

from app.sources.policies import (
    _candidate_key,
    _dedupe_policy_topics,
    _recency_first_score,
    _same_policy_topic,
)


def _policy(title, created_at, focus="美国跨境新规", authority="CBP"):
    return {
        "title": title,
        "created_at": created_at,
        "metrics": {
            "policy_focus": focus,
            "policy_authority": authority,
        },
    }


def test_similar_policy_titles_are_treated_as_same_topic():
    older = _policy(
        "CBP Updates De Minimis Import Requirements for E-Commerce Shipments",
        "2026-08-20T08:00:00+00:00",
    )
    newer = _policy(
        "New De Minimis Import Requirements for Ecommerce Shipments from CBP",
        "2026-08-26T08:00:00+00:00",
    )
    assert _same_policy_topic(older, newer) is True


def test_same_policy_topic_keeps_only_newest_item():
    older = _policy(
        "CBP Updates De Minimis Import Requirements for E-Commerce Shipments",
        "2026-08-20T08:00:00+00:00",
    )
    newer = _policy(
        "New De Minimis Import Requirements for Ecommerce Shipments from CBP",
        "2026-08-26T08:00:00+00:00",
    )
    kept, duplicate_count = _dedupe_policy_topics([older, newer])
    assert duplicate_count == 1
    assert len(kept) == 1
    assert kept[0]["created_at"] == newer["created_at"]


def test_different_policy_focus_is_not_deduplicated():
    amazon = _policy(
        "New Product Testing Requirements",
        "2026-08-26T08:00:00+00:00",
        focus="Amazon政策与审核",
        authority="Amazon",
    )
    cpsc = _policy(
        "New Product Testing Requirements",
        "2026-08-26T09:00:00+00:00",
        focus="产品合规审核",
        authority="CPSC",
    )
    kept, duplicate_count = _dedupe_policy_topics([amazon, cpsc])
    assert duplicate_count == 0
    assert len(kept) == 2


def test_same_focus_but_different_regulator_is_not_deduplicated():
    cpsc = _policy(
        "New Product Certification Requirements",
        "2026-08-26T08:00:00+00:00",
        focus="产品合规审核",
        authority="CPSC",
    )
    fcc = _policy(
        "New Product Certification Requirements",
        "2026-08-26T09:00:00+00:00",
        focus="产品合规审核",
        authority="FCC",
    )

    assert _same_policy_topic(cpsc, fcc) is False
    kept, duplicate_count = _dedupe_policy_topics([cpsc, fcc])
    assert duplicate_count == 0
    assert len(kept) == 2


def test_candidate_key_prevents_same_title_from_overwriting_different_regulators():
    title = "New Product Certification Requirements"
    cpsc_key = _candidate_key(title, "CPSC", "https://example.com/cpsc")
    fcc_key = _candidate_key(title, "FCC", "https://example.com/fcc")
    assert cpsc_key != fcc_key
    assert cpsc_key.startswith("cpsc:")
    assert fcc_key.startswith("fcc:")


def test_recency_sort_score_prioritizes_newer_policy_even_with_lower_quality():
    older = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
    newer = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    older_score = _recency_first_score(older, 100, 200)
    newer_score = _recency_first_score(newer, 1, 1)
    assert newer_score > older_score

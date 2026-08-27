from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, IntelligenceItem
from app.history_novelty import filter_recently_reported
from app.models.radar_item import RadarItem


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _history_metrics(*, use_case="Listing/内容", lane="跨境业务工具", reported=True, processed_at=None):
    return {
        "primary_use_case": use_case,
        "primary_lane": lane,
        "report_eligible": True,
        "final_report_eligible": reported,
        "history_processed_at": (
            processed_at
            or datetime.now(timezone.utc).isoformat()
        ),
    }


def _save_history(
    db,
    *,
    title,
    url,
    description,
    metrics,
    created_at=None,
):
    db.add(
        IntelligenceItem(
            source="github",
            title=title,
            url=url,
            description=description,
            category="ai",
            metrics=metrics,
            analysis={
                "purpose": "已完成分析",
                "summary": "具有明确价值",
                "business_score": 84,
                "opportunity": "high",
                "llm_meta": {"success": True, "fallback": False},
            },
            created_at=created_at or datetime.utcnow(),
        )
    )
    db.commit()


def _current(*, title, url, description, use_case="Listing/内容", lane="跨境业务工具"):
    return RadarItem(
        title=title,
        source="producthunt",
        url=url,
        description=description,
        category="ai",
        metrics={
            "report_eligible": True,
            "primary_use_case": use_case,
            "primary_lane": lane,
        },
        created_at=datetime.utcnow(),
    )


def test_different_project_same_recent_opportunity_is_suppressed():
    db = _session()
    previous_description = (
        "Amazon seller listing optimization workflow that generates localized titles, bullet points, "
        "keyword recommendations and multilingual product page content for marketplace operators."
    )
    _save_history(
        db,
        title="Seller Page Optimizer",
        url="https://github.com/acme/seller-page-optimizer",
        description=previous_description,
        metrics=_history_metrics(),
    )

    current = _current(
        title="Mercury Commerce Writer",
        url="https://mercury.example.com",
        description=(
            "Amazon seller listing optimization workflow that generates localized titles, bullet points, "
            "keyword recommendations and multilingual product page content for marketplace operators."
        ),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == []
    assert duplicate_count == 1
    assert current.metrics["history_opportunity_fatigue"] is True
    assert "Listing/内容" in current.metrics["history_opportunity_fatigue_reason"]
    db.close()


def test_same_use_case_but_different_capability_is_not_suppressed():
    db = _session()
    _save_history(
        db,
        title="Seller Page Optimizer",
        url="https://github.com/acme/seller-page-optimizer",
        description=(
            "Amazon seller listing optimization workflow that generates localized titles, bullet points, "
            "keyword recommendations and multilingual product page content for marketplace operators."
        ),
        metrics=_history_metrics(),
    )

    current = _current(
        title="Visual A Plus Inspector",
        url="https://visual.example.com",
        description=(
            "Computer vision quality assurance system for ecommerce teams that inspects product images, "
            "detects prohibited visual elements, measures image composition and validates A Plus media assets."
        ),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == [current]
    assert duplicate_count == 0
    db.close()


def test_same_copy_in_different_use_case_is_not_suppressed():
    db = _session()
    description = (
        "Amazon seller automation platform with reusable workflows, multilingual processing, analytics "
        "and marketplace integrations for ecommerce operations teams managing large catalogs."
    )
    _save_history(
        db,
        title="Listing Workflow",
        url="https://github.com/acme/listing-workflow",
        description=description,
        metrics=_history_metrics(use_case="Listing/内容"),
    )

    current = _current(
        title="Inventory Workflow",
        url="https://inventory.example.com",
        description=description,
        use_case="库存/履约",
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == [current]
    assert duplicate_count == 0
    db.close()


def test_previous_project_rejected_by_final_gate_does_not_block_new_candidate():
    db = _session()
    description = (
        "Amazon seller listing optimization workflow that generates localized titles, bullet points, "
        "keyword recommendations and multilingual product page content for marketplace operators."
    )
    _save_history(
        db,
        title="Weak Listing Wrapper",
        url="https://github.com/acme/weak-wrapper",
        description=description,
        metrics=_history_metrics(reported=False),
    )

    current = _current(
        title="Production Listing Engine",
        url="https://production.example.com",
        description=description,
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == [current]
    assert duplicate_count == 0
    db.close()


def test_opportunity_fatigue_expires_after_short_window():
    db = _session()
    old_processed = datetime.now(timezone.utc) - timedelta(days=8)
    description = (
        "Amazon seller listing optimization workflow that generates localized titles, bullet points, "
        "keyword recommendations and multilingual product page content for marketplace operators."
    )
    _save_history(
        db,
        title="Older Listing Engine",
        url="https://github.com/acme/older-listing-engine",
        description=description,
        metrics=_history_metrics(processed_at=old_processed.isoformat()),
        created_at=datetime.utcnow() - timedelta(days=8),
    )

    current = _current(
        title="New Listing Engine",
        url="https://new-listing.example.com",
        description=description,
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == [current]
    assert duplicate_count == 0
    db.close()


def test_missing_current_identity_is_filled_by_existing_relevance_gate():
    db = _session()
    description = (
        "Amazon product listing optimization and localization workflow for sellers that generates titles, "
        "bullet points, keyword recommendations and multilingual marketplace content with reusable automation."
    )
    _save_history(
        db,
        title="Existing Listing Optimizer",
        url="https://github.com/acme/existing-listing-optimizer",
        description=description,
        metrics=_history_metrics(),
    )

    current = RadarItem(
        title="Fresh Seller Content Suite",
        source="producthunt",
        url="https://seller-content.example.com",
        description=description,
        category="ai",
        metrics={"upvotes": 80, "comments": 12},
        created_at=datetime.utcnow(),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])

    assert fresh == []
    assert duplicate_count == 1
    assert current.metrics["report_eligible"] is True
    assert current.metrics["primary_lane"] == "跨境业务工具"
    assert current.metrics["primary_use_case"] == "Listing/内容"
    db.close()

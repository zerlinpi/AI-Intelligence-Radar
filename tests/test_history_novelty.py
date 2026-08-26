from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, IntelligenceItem
from app.history_novelty import filter_recently_reported
from app.models.radar_item import RadarItem


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _save_success(db, *, title, url, description, category="ai", source="github", metrics=None):
    db.add(
        IntelligenceItem(
            source=source,
            title=title,
            url=url,
            description=description,
            category=category,
            metrics=metrics or {},
            analysis={
                "purpose": "已完成分析",
                "summary": "存在明确价值",
                "business_score": 80,
                "opportunity": "high",
                "llm_meta": {"success": True, "fallback": False},
            },
            created_at=datetime.utcnow(),
        )
    )
    db.commit()


def test_cross_source_same_project_is_not_reported_again_next_day():
    db = _session()
    _save_success(
        db,
        title="acme/seller-copilot",
        url="https://github.com/acme/seller-copilot",
        description="Amazon seller listing automation with keyword research and multilingual localization workflow",
    )

    current = RadarItem(
        title="Seller Copilot",
        source="producthunt",
        url="https://seller-copilot.example.com",
        description="Amazon seller listing automation with keyword research and multilingual localization for product pages",
        created_at=datetime.utcnow(),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])
    assert fresh == []
    assert duplicate_count == 1
    db.close()


def test_generic_same_title_with_unrelated_description_is_not_suppressed():
    db = _session()
    _save_success(
        db,
        title="AI Seller Assistant",
        url="https://example.com/listing-assistant",
        description="Amazon listing localization and keyword research software for ecommerce sellers",
    )

    current = RadarItem(
        title="AI Seller Assistant",
        source="github",
        url="https://github.com/acme/warehouse-assistant",
        description="Warehouse robotics control runtime for autonomous industrial picking arms and motion planning",
        created_at=datetime.utcnow(),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])
    assert fresh == [current]
    assert duplicate_count == 0
    db.close()


def test_policy_reworded_same_topic_is_suppressed_across_days():
    db = _session()
    _save_success(
        db,
        title="New De Minimis Import Requirements for Ecommerce Shipments",
        url="https://example.com/cbp-old",
        description="CBP updates de minimis ecommerce import filing requirements for low value shipments entering the United States.",
        category="policy",
        source="us_import_rule",
        metrics={"policy_focus": "美国跨境新规", "policy_authority": "CBP"},
    )

    current = RadarItem(
        title="CBP Updates De Minimis Import Requirements for E-Commerce Shipments",
        source="us_import_rule",
        url="https://example.com/cbp-rewrite",
        description="Updated CBP requirements cover de minimis ecommerce import filing for low-value shipments entering the United States.",
        category="policy",
        metrics={"policy_focus": "美国跨境新规", "policy_authority": "CBP"},
        created_at=datetime.utcnow(),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])
    assert fresh == []
    assert duplicate_count == 1
    db.close()


def test_same_words_in_different_policy_focus_are_not_suppressed():
    db = _session()
    _save_success(
        db,
        title="New Product Certification Requirements",
        url="https://example.com/amazon-certification",
        description="Amazon seller product certification requirements for marketplace listings and account compliance.",
        category="policy",
        source="amazon_policy",
        metrics={"policy_focus": "Amazon政策与审核", "policy_authority": "Amazon"},
    )

    current = RadarItem(
        title="New Product Certification Requirements",
        source="cpsc_compliance",
        url="https://example.com/cpsc-certification",
        description="CPSC certification requirements for regulated consumer product imports and certificate filing.",
        category="policy",
        metrics={"policy_focus": "产品合规审核", "policy_authority": "CPSC"},
        created_at=datetime.utcnow(),
    )

    fresh, duplicate_count = filter_recently_reported(db, [current])
    assert fresh == [current]
    assert duplicate_count == 0
    db.close()

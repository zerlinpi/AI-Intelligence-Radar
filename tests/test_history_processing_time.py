from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, IntelligenceItem
from app.history_novelty import filter_recently_reported
from app.models.radar_item import RadarItem
from app.storage.repository import save_item


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _success_analysis():
    return {
        "purpose": "已完成分析",
        "summary": "存在明确价值",
        "business_score": 82,
        "opportunity": "high",
        "llm_meta": {"success": True, "fallback": False},
    }


def test_recent_processing_time_suppresses_old_source_cross_day_duplicate():
    db = _session()
    old_source_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=180)
    processed_yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.add(
        IntelligenceItem(
            source="github",
            title="acme/seller-intelligence",
            url="https://github.com/acme/seller-intelligence",
            description="Amazon seller listing intelligence with keyword research and multilingual localization workflow",
            category="ai",
            metrics={"history_processed_at": processed_yesterday},
            analysis=_success_analysis(),
            created_at=old_source_time,
        )
    )
    db.commit()

    current = RadarItem(
        title="Seller Intelligence",
        source="producthunt",
        url="https://seller-intelligence.example.com",
        description="Amazon seller listing intelligence with keyword research and multilingual localization workflow",
        created_at=datetime.now(timezone.utc),
    )

    fresh, duplicates = filter_recently_reported(db, [current], lookback_days=30)
    assert fresh == []
    assert duplicates == 1
    db.close()


def test_expired_processing_time_does_not_extend_semantic_history_window():
    db = _session()
    processed_long_ago = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    db.add(
        IntelligenceItem(
            source="github",
            title="acme/seller-intelligence",
            url="https://github.com/acme/seller-intelligence",
            description="Amazon seller listing intelligence with keyword research and multilingual localization workflow",
            category="ai",
            metrics={"history_processed_at": processed_long_ago},
            analysis=_success_analysis(),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=180),
        )
    )
    db.commit()

    current = RadarItem(
        title="Seller Intelligence",
        source="producthunt",
        url="https://seller-intelligence-new.example.com",
        description="Amazon seller listing intelligence with keyword research and multilingual localization workflow",
        created_at=datetime.now(timezone.utc),
    )

    fresh, duplicates = filter_recently_reported(db, [current], lookback_days=30)
    assert fresh == [current]
    assert duplicates == 0
    db.close()


def test_storage_records_processing_time_without_overwriting_source_time():
    db = _session()
    source_time = datetime.now(timezone.utc) - timedelta(days=90)
    item = RadarItem(
        title="Old Research Newly Processed",
        source="arxiv",
        url="https://arxiv.org/abs/0000.00000",
        description="Embedded edge vision for a physical camera product with on-device inference and sensor integration",
        created_at=source_time,
        analysis=_success_analysis(),
    )

    record = save_item(db, item)
    processed_at = datetime.fromisoformat(record.metrics["history_processed_at"])

    assert abs((processed_at - datetime.now(timezone.utc)).total_seconds()) < 10
    assert record.created_at == source_time.astimezone(timezone.utc).replace(tzinfo=None)
    db.close()

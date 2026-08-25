from sqlalchemy.orm import Session

from app.database.models import IntelligenceItem
from app.models.radar_item import RadarItem


def _to_dict(item):
    """Convert RadarItem or dict into storage-ready dictionary."""
    if isinstance(item, RadarItem):
        return item.to_dict()

    return item or {}


def save_item(db: Session, item):
    data = _to_dict(item)

    analysis = data.get("analysis", {}) or {}

    record = IntelligenceItem(
        source=data.get("source", "unknown"),
        title=data.get("title", ""),
        url=data.get("url", ""),
        description=data.get("description", ""),
        trend_score=data.get("trend_score", 0),
        business_score=analysis.get(
            "business_score",
            data.get("business_score", 0),
        ),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def exists(db: Session, url: str):
    if not url:
        return False

    return (
        db.query(IntelligenceItem)
        .filter(IntelligenceItem.url == url)
        .first()
        is not None
    )


def save_batch(db: Session, items: list):
    saved = []

    for item in items:
        data = _to_dict(item)

        if not exists(db, data.get("url", "")):
            saved.append(save_item(db, item))

    return saved

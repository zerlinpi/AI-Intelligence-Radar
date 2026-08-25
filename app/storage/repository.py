from sqlalchemy.orm import Session

from app.database.models import IntelligenceItem


def save_item(db: Session, item: dict):
    record = IntelligenceItem(
        source=item.get("source", "unknown"),
        title=item.get("title", ""),
        url=item.get("url", ""),
        description=item.get("description", ""),
        trend_score=item.get("trend_score", 0),
        business_score=item.get("business_score", 0),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def exists(db: Session, url: str):
    return db.query(IntelligenceItem).filter(IntelligenceItem.url == url).first() is not None


def save_batch(db: Session, items: list):
    saved = []
    for item in items:
        if not exists(db, item.get("url", "")):
            saved.append(save_item(db, item))
    return saved

from sqlalchemy.orm import Session

from app.database.models import IntelligenceItem
from app.models.radar_item import RadarItem
from app.core.logger import get_logger


logger = get_logger("storage")


def _to_dict(item):
    """Convert RadarItem or dict into storage-ready dictionary."""
    if isinstance(item, RadarItem):
        return item.to_dict()

    if isinstance(item, dict):
        return item

    return {}


def _safe_dict(value):
    """Ensure JSON fields are always stored as dictionaries."""
    return value if isinstance(value, dict) else {}


def save_item(db: Session, item):
    data = _to_dict(item)
    if not data:
        raise ValueError("storage item must be a RadarItem or dictionary")

    analysis = _safe_dict(data.get("analysis"))
    metrics = _safe_dict(data.get("metrics"))

    record = IntelligenceItem(
        source=data.get("source", "unknown") or "unknown",
        title=data.get("title", "") or "",
        url=data.get("url", "") or "",
        description=data.get("description", "") or "",
        category=data.get("category", "ai") or "ai",
        trend_score=data.get("trend_score", 0) or 0,
        business_score=analysis.get(
            "business_score",
            data.get("business_score", 0) or 0,
        ),
        metrics=metrics,
        analysis=analysis,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise

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

    for item in items or []:
        data = _to_dict(item)
        if not data:
            logger.warning("storage skipped invalid item type=%s", type(item).__name__)
            continue

        url = data.get("url", "") or ""
        title = data.get("title", "") or ""

        try:
            if not exists(db, url):
                saved.append(save_item(db, item))
        except Exception:
            db.rollback()
            logger.exception(
                "storage failed title=%s url=%s",
                title,
                url,
            )
            continue

    return saved

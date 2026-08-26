from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.models import IntelligenceItem
from app.models.radar_item import RadarItem
from app.core.logger import get_logger


logger = get_logger("数据存储")


def _to_dict(item):
    """将 RadarItem 或字典转换为可存储的数据。"""
    if isinstance(item, RadarItem):
        return item.to_dict()

    if isinstance(item, dict):
        return item

    return {}


def _safe_dict(value):
    """确保 JSON 字段始终使用字典。"""
    return value if isinstance(value, dict) else {}


def _source_created_at(value):
    """将来源发布时间统一转换为 SQLite 使用的 UTC 时间。"""
    if isinstance(value, datetime):
        created = value
    elif isinstance(value, str) and value.strip():
        try:
            created = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)

    return created


def save_item(db: Session, item):
    data = _to_dict(item)
    if not data:
        raise ValueError("待保存项目必须是 RadarItem 或字典")

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

    source_created_at = _source_created_at(data.get("created_at"))
    if source_created_at is not None:
        record.created_at = source_created_at

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
            logger.warning("已跳过无效存储项目：类型=%s", type(item).__name__)
            continue

        url = data.get("url", "") or ""
        title = data.get("title", "") or ""

        try:
            if not exists(db, url):
                saved.append(save_item(db, item))
        except Exception:
            db.rollback()
            logger.exception(
                "项目保存失败：标题=%s 链接=%s",
                title,
                url,
            )
            continue

    return saved

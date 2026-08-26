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


def _analysis_is_fallback(value) -> bool:
    analysis = _safe_dict(value)
    meta = _safe_dict(analysis.get("llm_meta"))

    if meta.get("fallback") is True:
        return True

    # 兼容较早版本由主流程生成、尚未带 llm_meta 的降级结果。
    if analysis.get("error"):
        return True

    purpose = str(analysis.get("purpose") or "")
    summary = str(analysis.get("summary") or "")
    fallback_markers = (
        "暂无法生成",
        "AI 分析暂不可用",
        "AI 深度分析未完成",
        "AI 结构化分析未完成",
    )
    return any(marker in purpose or marker in summary for marker in fallback_markers)


def _find_by_url(db: Session, url: str):
    if not url:
        return None

    return (
        db.query(IntelligenceItem)
        .filter(IntelligenceItem.url == url)
        .first()
    )


def _fill_record(record: IntelligenceItem, data: dict):
    analysis = _safe_dict(data.get("analysis"))
    metrics = _safe_dict(data.get("metrics"))

    record.source = data.get("source", "unknown") or "unknown"
    record.title = data.get("title", "") or ""
    record.url = data.get("url", "") or ""
    record.description = data.get("description", "") or ""
    record.category = data.get("category", "ai") or "ai"
    record.trend_score = data.get("trend_score", 0) or 0
    record.business_score = analysis.get(
        "business_score",
        data.get("business_score", 0) or 0,
    )
    record.metrics = metrics
    record.analysis = analysis

    source_created_at = _source_created_at(data.get("created_at"))
    if source_created_at is not None:
        record.created_at = source_created_at

    return record


def save_item(db: Session, item):
    data = _to_dict(item)
    if not data:
        raise ValueError("待保存项目必须是 RadarItem 或字典")

    url = data.get("url", "") or ""
    existing = _find_by_url(db, url) if url else None

    # 旧记录若是模型失败的降级结果，本次成功分析后直接原地覆盖，
    # 避免 unique URL 约束产生重复记录或让失败结果永久封死。
    if existing is not None and _analysis_is_fallback(getattr(existing, "analysis", {})):
        record = _fill_record(existing, data)
        logger.info("覆盖旧降级记录：标题=%s 链接=%s", record.title, record.url)
    else:
        record = _fill_record(IntelligenceItem(), data)

    try:
        if existing is None:
            db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise

    return record


def exists(db: Session, url: str):
    """只有已经成功分析的 URL 才算真正完成。

    历史记录若是 AI fallback，则返回 False，让下一次采集重新进入分析流程。
    """
    record = _find_by_url(db, url)
    if record is None:
        return False

    return not _analysis_is_fallback(getattr(record, "analysis", {}))


def save_batch(db: Session, items: list):
    saved = []

    for item in items or []:
        data = _to_dict(item)
        if not data:
            logger.warning("已跳过无效存储项目：类型=%s", type(item).__name__)
            continue

        url = data.get("url", "") or ""
        title = data.get("title", "") or ""
        analysis = _safe_dict(data.get("analysis"))

        # AI 失败不等于该项目已处理完成。失败条目仍可发到飞书作为降级展示，
        # 但不新建“成功历史”；已有旧 fallback 也保留为可重试状态。
        if _analysis_is_fallback(analysis):
            logger.warning(
                "未保存AI降级结果，后续将自动重试：标题=%s 链接=%s",
                title,
                url,
            )
            continue

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

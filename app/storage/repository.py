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


def _processed_at_iso() -> str:
    """Radar 实际完成本次成功分析/处理的 UTC 时间。"""
    return datetime.now(timezone.utc).isoformat()


def _analysis_is_fallback(value) -> bool:
    analysis = _safe_dict(value)
    meta = _safe_dict(analysis.get("llm_meta"))

    if meta.get("fallback") is True:
        return True

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


def _is_material_update(data: dict) -> bool:
    metrics = _safe_dict(data.get("metrics"))
    return metrics.get("history_material_update") is True


def _fill_record(record: IntelligenceItem, data: dict):
    analysis = _safe_dict(data.get("analysis"))
    # 复制一份，避免存储层给调用方持有的 metrics 原地追加内部字段。
    metrics = dict(_safe_dict(data.get("metrics")))
    metrics["history_processed_at"] = _processed_at_iso()

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

    # created_at 始终保留“来源发布时间”的语义；历史回看窗口使用 metrics.history_processed_at。
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
    material_update = _is_material_update(data)

    # 两种情况必须原地覆盖：
    # 1) 旧记录是 AI fallback，本轮成功后替换失败快照；
    # 2) 历史新颖性判断确认同 URL 存在重大更新，用最新快照替换旧快照。
    if existing is not None and (
        _analysis_is_fallback(getattr(existing, "analysis", {}))
        or material_update
    ):
        record = _fill_record(existing, data)
        reason = str((_safe_dict(data.get("metrics"))).get("history_material_update_reason") or "")
        if material_update:
            logger.info(
                "覆盖重大更新历史快照：标题=%s 链接=%s 原因=%s",
                record.title,
                record.url,
                reason or "检测到实质更新",
            )
        else:
            logger.info("覆盖旧降级记录：标题=%s 链接=%s", record.title, record.url)
    elif existing is not None:
        # 正常成功记录不应重复插入，避免触发 URL 唯一键异常。
        return existing
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
        material_update = _is_material_update(data)

        # AI 失败不等于该项目已处理完成；失败记录不进入成功历史，方便后续自动重试。
        if _analysis_is_fallback(analysis):
            logger.warning(
                "未保存AI降级结果，后续将自动重试：标题=%s 链接=%s",
                title,
                url,
            )
            continue

        try:
            if material_update or not exists(db, url):
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

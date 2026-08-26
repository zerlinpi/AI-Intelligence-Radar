from datetime import datetime, timedelta
import re
from typing import Iterable, Tuple

from sqlalchemy.orm import Session

from app.content_quality import copy_similarity
from app.database.models import IntelligenceItem
from app.models.radar_item import RadarItem
from app.storage.repository import exists


PROJECT_HISTORY_DAYS = 30
POLICY_HISTORY_DAYS = 120
MAX_HISTORY_RECORDS = 800

_POLICY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with", "new", "news", "update", "updates",
    "policy", "policies", "rule", "rules", "requirement", "requirements", "compliance",
    "amazon", "seller", "sellers", "selling", "product", "products", "official",
}


def _item_dict(item):
    if isinstance(item, RadarItem):
        return item.to_dict()
    return item if isinstance(item, dict) else {}


def _canonical_title(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^show\s+hn\s*:\s*", "", text)
    if "/" in text and " " not in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _policy_tokens(value: str) -> set:
    return {
        token
        for token in _canonical_title(value).split()
        if len(token) >= 3 and token not in _POLICY_STOPWORDS
    }


def _record_dict(record: IntelligenceItem) -> dict:
    return {
        "title": record.title or "",
        "url": record.url or "",
        "description": record.description or "",
        "category": record.category or "ai",
        "source": record.source or "unknown",
        "metrics": record.metrics if isinstance(record.metrics, dict) else {},
    }


def _same_policy_topic(current: dict, previous: dict) -> bool:
    current_metrics = current.get("metrics") or {}
    previous_metrics = previous.get("metrics") or {}
    current_focus = str(current_metrics.get("policy_focus") or "").strip()
    previous_focus = str(previous_metrics.get("policy_focus") or "").strip()
    if current_focus and previous_focus and current_focus != previous_focus:
        return False

    left = _canonical_title(current.get("title"))
    right = _canonical_title(previous.get("title"))
    if not left or not right:
        return False
    if left == right:
        return True

    left_tokens = _policy_tokens(left)
    right_tokens = _policy_tokens(right)
    overlap = len(left_tokens & right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    jaccard = overlap / max(len(left_tokens | right_tokens), 1)
    title_similarity = copy_similarity(left, right)

    if containment >= 0.75 or (overlap >= 3 and jaccard >= 0.48):
        return True
    if title_similarity >= 0.82:
        return True

    # 标题变动较大时，需要正文也支持“同一政策主题”，避免把同机构不同规则误合并。
    return (
        title_similarity >= 0.68
        and copy_similarity(
            str(current.get("description") or ""),
            str(previous.get("description") or ""),
        ) >= 0.58
    )


def _same_project(current: dict, previous: dict) -> bool:
    current_url = str(current.get("url") or "").strip()
    previous_url = str(previous.get("url") or "").strip()
    if current_url and previous_url and current_url == previous_url:
        return True

    left = _canonical_title(current.get("title"))
    right = _canonical_title(previous.get("title"))
    if not left or not right:
        return False

    description_similarity = copy_similarity(
        str(current.get("description") or ""),
        str(previous.get("description") or ""),
    )

    # 完全同名项目仍要求正文有一定一致性，防止“AI Assistant”这类泛名称误合并。
    if left == right:
        return description_similarity >= 0.30

    title_similarity = copy_similarity(left, right)
    if title_similarity < 0.88:
        return False
    return description_similarity >= 0.44


def _same_historical_item(current: dict, previous: dict) -> bool:
    current_category = str(current.get("category") or "ai").lower()
    previous_category = str(previous.get("category") or "ai").lower()
    if current_category != previous_category:
        return False
    if current_category == "policy":
        return _same_policy_topic(current, previous)
    return _same_project(current, previous)


def _recent_records(db: Session, category: str, days: int) -> list:
    cutoff = datetime.utcnow() - timedelta(days=max(int(days), 1))
    return (
        db.query(IntelligenceItem)
        .filter(IntelligenceItem.category == category)
        .filter(IntelligenceItem.created_at >= cutoff)
        .order_by(IntelligenceItem.created_at.desc())
        .limit(MAX_HISTORY_RECORDS)
        .all()
    )


def filter_recently_reported(
    db: Session,
    items: Iterable,
    *,
    lookback_days: int | None = None,
) -> Tuple[list, int]:
    """过滤已经成功处理过的 URL，以及近期跨来源/改标题后的同一主题。

    数据库只保存成功分析记录，因此这里不会阻止 AI fallback 条目的后续自动重试。
    """
    rows = list(items or [])
    if not rows:
        return [], 0

    categories = {
        str(_item_dict(item).get("category") or "ai").lower()
        for item in rows
    }
    histories = {}
    for category in categories:
        days = lookback_days
        if days is None:
            days = POLICY_HISTORY_DAYS if category == "policy" else PROJECT_HISTORY_DAYS
        histories[category] = [
            _record_dict(record)
            for record in _recent_records(db, category, days)
        ]

    fresh = []
    duplicates = 0
    for item in rows:
        data = _item_dict(item)
        url = str(data.get("url") or "").strip()
        if url and exists(db, url):
            duplicates += 1
            continue

        category = str(data.get("category") or "ai").lower()
        if any(
            _same_historical_item(data, previous)
            for previous in histories.get(category, [])
        ):
            duplicates += 1
            continue

        fresh.append(item)

    return fresh, duplicates

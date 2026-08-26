import re
from datetime import datetime, timezone
from typing import List

from app.content_quality import copy_similarity
from app.models.radar_item import RadarItem


_SOURCE_QUALITY = {
    "github": 60,
    "producthunt": 55,
    "huggingface": 50,
    "arxiv": 45,
    "hackernews": 35,
}


def _canonical_title(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^show\s+hn\s*:\s*", "", text)
    # GitHub 常见 owner/repo 形式只保留 repo 名，方便和 HN/Product Hunt 的产品名对齐。
    if "/" in text and " " not in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _title_tokens(value: str) -> set:
    return {
        token
        for token in _canonical_title(value).split()
        if len(token) >= 2
    }


def _descriptions_support_same_project(left: dict, right: dict) -> bool:
    left_desc = str(left.get("description") or "")
    right_desc = str(right.get("description") or "")
    if not left_desc or not right_desc:
        return False
    return copy_similarity(left_desc, right_desc) >= 0.42


def _same_project(left: dict, right: dict) -> bool:
    left_title = _canonical_title(left.get("title"))
    right_title = _canonical_title(right.get("title"))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True

    left_tokens = _title_tokens(left_title)
    right_tokens = _title_tokens(right_title)
    overlap = len(left_tokens & right_tokens)
    if overlap >= 3:
        containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
        if containment >= 0.85 and _descriptions_support_same_project(left, right):
            return True

    # 非完全同名项目必须同时满足标题和简介相似，避免“AI Seller Assistant”这类泛名称误合并。
    if copy_similarity(left_title, right_title) >= 0.88:
        return _descriptions_support_same_project(left, right)
    return False


def _item_quality(item: dict) -> float:
    source = str(item.get("source") or "").lower()
    description = str(item.get("description") or "")
    metrics = item.get("metrics") or {}
    metric_count = 0
    if isinstance(metrics, dict):
        metric_count = sum(
            1
            for value in metrics.values()
            if value not in (None, "", 0, 0.0, [], {})
        )
    return (
        _SOURCE_QUALITY.get(source, 20)
        + min(len(description), 1800) / 60
        + min(metric_count, 10) * 2
    )


def _merge_duplicate(left: dict, right: dict) -> dict:
    """同一项目跨来源出现时保留信息更完整的一条，并记录其他来源。"""
    primary, secondary = (left, right)
    if _item_quality(right) > _item_quality(left):
        primary, secondary = right, left

    merged = dict(primary)
    metrics = dict(primary.get("metrics") or {})
    secondary_metrics = secondary.get("metrics") or {}
    if isinstance(secondary_metrics, dict):
        for key, value in secondary_metrics.items():
            if key not in metrics or metrics.get(key) in (None, "", 0, 0.0, [], {}):
                metrics[key] = value

    sources = []
    for source in (
        primary.get("source"),
        secondary.get("source"),
        *((primary.get("metrics") or {}).get("also_seen_on") or []),
        *((secondary.get("metrics") or {}).get("also_seen_on") or []),
    ):
        source = str(source or "").strip()
        if source and source not in sources:
            sources.append(source)
    if len(sources) > 1:
        metrics["also_seen_on"] = sources

    primary_desc = str(primary.get("description") or "")
    secondary_desc = str(secondary.get("description") or "")
    if len(secondary_desc) > len(primary_desc):
        merged["description"] = secondary_desc

    merged["metrics"] = metrics
    return merged


def normalize_items(items) -> List[dict]:
    """统一数据结构，并去掉 URL 重复与跨来源的同项目重复。"""
    exact_seen = set()
    result = []

    for raw in items or []:
        if isinstance(raw, RadarItem):
            item = raw
        elif isinstance(raw, dict):
            item = RadarItem.from_dict(raw)
        else:
            continue

        item.title = (item.title or "").strip()
        item.url = (item.url or "").strip()
        item.description = (item.description or "").strip()

        if not item.title:
            continue

        key = item.url or _canonical_title(item.title)
        if key in exact_seen:
            continue

        data = item.to_dict()
        data.setdefault(
            "collected_at",
            datetime.now(timezone.utc).isoformat(),
        )

        duplicate_index = next(
            (
                index
                for index, existing in enumerate(result)
                if _same_project(existing, data)
            ),
            None,
        )
        if duplicate_index is not None:
            result[duplicate_index] = _merge_duplicate(result[duplicate_index], data)
            exact_seen.add(key)
            continue

        exact_seen.add(key)
        result.append(data)

    return result

from datetime import datetime
from typing import List

from app.models.radar_item import RadarItem


def normalize_items(items) -> List[dict]:
    """Normalize raw collector data into unified RadarItem dictionaries."""

    seen = set()
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

        # Prefer URL for deduplication. For items without URL, use
        # normalized title instead of an empty key to avoid dropping
        # unrelated no-url items.
        key = item.url or item.title.lower()

        if key in seen:
            continue

        seen.add(key)

        data = item.to_dict()
        data.setdefault("collected_at", datetime.utcnow().isoformat())

        result.append(data)

    return result

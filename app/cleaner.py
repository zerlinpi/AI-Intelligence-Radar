from datetime import datetime
from typing import List, Union

from app.models.radar_item import RadarItem


def normalize_items(items) -> List[dict]:
    """Normalize raw collector data into unified RadarItem dictionaries."""

    seen = set()
    result = []

    for raw in items:
        if isinstance(raw, RadarItem):
            item = raw
        elif isinstance(raw, dict):
            item = RadarItem.from_dict(raw)
        else:
            continue

        if not item.title:
            continue

        key = item.url or item.title.lower()

        if key in seen:
            continue

        seen.add(key)

        data = item.to_dict()
        data.setdefault("collected_at", datetime.utcnow().isoformat())

        result.append(data)

    return result

from datetime import datetime


def normalize_items(items):
    """Normalize intelligence items and remove invalid duplicates."""
    seen = set()
    result = []

    for item in items:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()

        if not title:
            continue

        key = url or title.lower()
        if key in seen:
            continue

        seen.add(key)

        item.setdefault("source", "unknown")
        item.setdefault("description", "")
        item.setdefault("collected_at", datetime.utcnow().isoformat())
        item.setdefault("stars", 0)
        item.setdefault("forks", 0)
        item.setdefault("comments", 0)
        item.setdefault("downloads", 0)
        item.setdefault("upvotes", 0)

        result.append(item)

    return result

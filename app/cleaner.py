def normalize_items(items):
    """Remove invalid and duplicate intelligence items."""
    seen = set()
    result = []

    for item in items:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result

from datetime import datetime
from typing import Dict, List

_history: List[Dict] = []


def save_snapshot(item: Dict):
    item = dict(item)
    item["saved_at"] = datetime.utcnow().isoformat()
    _history.append(item)
    return item


def get_history():
    return _history


def exists_url(url: str) -> bool:
    return any(x.get("url") == url for x in _history)

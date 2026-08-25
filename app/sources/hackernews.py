from typing import List, Dict

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


logger = get_logger("hackernews")


class HackerNewsCollector(BaseCollector):
    name = "hackernews"

    def collect(self, limit: int = 10) -> List[Dict]:
        api = "https://hacker-news.firebaseio.com/v0/topstories.json"

        response = requests.get(api, timeout=10)
        response.raise_for_status()

        ids = response.json()
        if not isinstance(ids, list):
            return []

        results = []

        for item_id in ids[:limit]:
            try:
                response = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                    timeout=10,
                )
                response.raise_for_status()

                item = response.json()

                if not isinstance(item, dict):
                    continue

                results.append(
                    {
                        "source": self.name,
                        "title": item.get("title") or "",
                        "url": item.get("url") or "",
                        "description": item.get("title") or "",
                        "score": item.get("score") or 0,
                    }
                )
            except Exception:
                logger.exception("failed fetching hackernews item=%s", item_id)
                continue

        return results


def fetch_hackernews(limit=10):
    return HackerNewsCollector().collect_safe(limit)

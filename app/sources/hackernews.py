from typing import List, Dict

import requests

from app.sources.base import BaseCollector


class HackerNewsCollector(BaseCollector):
    name = "hackernews"

    def collect(self, limit: int = 10) -> List[Dict]:
        api = "https://hacker-news.firebaseio.com/v0/topstories.json"

        ids = requests.get(api, timeout=10).json()[:limit]
        results = []

        for item_id in ids:
            response = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                timeout=10,
            )
            item = response.json()

            if item:
                results.append(
                    {
                        "source": self.name,
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("title", ""),
                        "score": item.get("score", 0),
                    }
                )

        return results


def fetch_hackernews(limit=10):
    return HackerNewsCollector().collect_safe(limit)

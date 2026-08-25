from typing import List, Dict

import requests

from app.sources.base import BaseCollector


API = "https://export.arxiv.org/api/query"


class ArxivCollector(BaseCollector):
    name = "arxiv"

    def collect(self, limit: int = 10) -> List[Dict]:
        params = {
            "search_query": "cat:cs.AI",
            "start": 0,
            "max_results": limit,
        }

        response = requests.get(API, params=params, timeout=20)
        response.raise_for_status()

        text = response.text or ""

        if not text.strip():
            return []

        return [
            {
                "source": self.name,
                "title": "AI Research Paper",
                "url": "",
                "description": text[:500],
            }
        ]


def fetch_ai_papers(limit=10):
    return ArxivCollector().collect_safe(limit)

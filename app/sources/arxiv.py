from app.sources.base import BaseCollector
import requests

API = "http://export.arxiv.org/api/query"


class ArxivCollector(BaseCollector):
    name = "arxiv"

    def collect(self, limit=10):
        params = {
            "search_query": "cat:cs.AI",
            "start": 0,
            "max_results": limit,
        }

        response = requests.get(API, params=params, timeout=20)
        response.raise_for_status()

        return [
            {
                "source": self.name,
                "title": "AI Research Paper",
                "url": "",
                "description": response.text[:500],
            }
        ]


def fetch_ai_papers(limit=10):
    return ArxivCollector().collect_safe(limit)

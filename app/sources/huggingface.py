from typing import List, Dict

import requests

from app.sources.base import BaseCollector


class HuggingFaceCollector(BaseCollector):
    name = "huggingface"

    def collect(self, limit: int = 10) -> List[Dict]:
        api = "https://huggingface.co/api/models"

        params = {
            "sort": "downloads",
            "direction": -1,
            "limit": limit,
        }

        response = requests.get(api, params=params, timeout=20)
        response.raise_for_status()

        return [
            {
                "source": self.name,
                "title": item.get("modelId", ""),
                "url": f"https://huggingface.co/{item.get('modelId', '')}",
                "description": item.get("pipeline_tag", ""),
                "downloads": item.get("downloads", 0),
            }
            for item in response.json()
        ]


def fetch_models(limit=10):
    return HuggingFaceCollector().collect_safe(limit)

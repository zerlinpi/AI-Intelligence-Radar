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

        payload = response.json()

        if not isinstance(payload, list):
            return []

        results = []

        for item in payload:
            if not isinstance(item, dict):
                continue

            model_id = item.get("modelId") or ""

            if not model_id:
                continue

            results.append(
                {
                    "source": self.name,
                    "title": model_id,
                    "url": f"https://huggingface.co/{model_id}",
                    "description": item.get("pipeline_tag") or "",
                    "downloads": item.get("downloads") or 0,
                }
            )

        return results


def fetch_models(limit=10):
    return HuggingFaceCollector().collect_safe(limit)

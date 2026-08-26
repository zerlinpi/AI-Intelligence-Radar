from datetime import datetime, timezone
from typing import Dict, List

import requests

from app.sources.base import BaseCollector


class HuggingFaceCollector(BaseCollector):
    name = "huggingface"

    def collect(self, limit: int = 10) -> List[Dict]:
        api = "https://huggingface.co/api/models"
        fetch_limit = min(max(limit * 5, 30), 100)

        params = {
            "sort": "createdAt",
            "direction": -1,
            "limit": fetch_limit,
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
            created_at = item.get("createdAt")
            if not model_id or not created_at:
                continue

            try:
                created = datetime.fromisoformat(
                    str(created_at).replace("Z", "+00:00")
                )
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)

                age_hours = max(
                    (datetime.now(timezone.utc) - created).total_seconds() / 3600,
                    1,
                )
            except Exception:
                continue

            # Keep this source focused on very recent model launches.
            if age_hours > 24 * 7:
                continue

            downloads = item.get("downloads") or 0
            likes = item.get("likes") or 0
            momentum = (downloads + likes * 200) / max(age_hours / 24, 0.25)

            results.append(
                {
                    "source": self.name,
                    "title": model_id,
                    "url": f"https://huggingface.co/{model_id}",
                    "description": item.get("pipeline_tag") or "新发布 AI 模型",
                    "created_at": created_at,
                    "downloads": downloads,
                    "metrics": {
                        "downloads": downloads,
                        "likes": likes,
                        "momentum": round(momentum, 2),
                    },
                }
            )

        results.sort(
            key=lambda x: (x.get("metrics") or {}).get("momentum", 0),
            reverse=True,
        )
        return results[:limit]


def fetch_models(limit=10):
    return HuggingFaceCollector().collect_safe(limit)

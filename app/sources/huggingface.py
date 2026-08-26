from datetime import datetime, timezone
from typing import Dict, List

import requests

from app.sources.base import BaseCollector
from app.relevance import attach_eligibility_metrics, report_eligibility


class HuggingFaceCollector(BaseCollector):
    name = "huggingface"

    def collect(self, limit: int = 15) -> List[Dict]:
        api = "https://huggingface.co/api/models"
        fetch_limit = min(max(limit * 8, 80), 100)

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
        rejected = 0

        for item in payload:
            if not isinstance(item, dict):
                continue

            model_id = item.get("modelId") or ""
            created_at = item.get("createdAt")
            if not model_id or not created_at:
                continue

            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max(
                    (datetime.now(timezone.utc) - created).total_seconds() / 3600,
                    1,
                )
            except Exception:
                continue

            if age_hours > 24 * 7:
                continue

            downloads = item.get("downloads") or 0
            likes = item.get("likes") or 0
            momentum = (downloads + likes * 200) / max(age_hours / 24, 0.25)

            pipeline_tag = item.get("pipeline_tag") or ""
            library_name = item.get("library_name") or ""
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                tags = []

            description_parts = []
            if pipeline_tag:
                description_parts.append(f"task: {pipeline_tag}")
            if library_name:
                description_parts.append(f"library: {library_name}")
            if tags:
                description_parts.append("tags: " + " ".join(str(tag) for tag in tags))
            if not description_parts:
                description_parts.append("新发布 AI 模型")

            record = {
                "source": self.name,
                "title": model_id,
                "url": f"https://huggingface.co/{model_id}",
                "description": " | ".join(description_parts),
                "created_at": created_at,
                "downloads": downloads,
                "metrics": {
                    "downloads": downloads,
                    "likes": likes,
                    "momentum": round(momentum, 2),
                    "pipeline_tag": pipeline_tag,
                    "library_name": library_name,
                    "tags": tags,
                },
            }

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            if not eligibility["eligible"]:
                rejected += 1
                continue

            results.append(record)

        # 模型首先看是否能真正进入跨境业务或实体产品开发，再看下载/点赞热度。
        results.sort(
            key=lambda x: (
                float((x.get("metrics") or {}).get("opportunity_score", 0) or 0),
                float((x.get("metrics") or {}).get("momentum", 0) or 0),
                x.get("created_at") or "",
            ),
            reverse=True,
        )

        # 这里的“淘汰”是资格门槛，不是因为模型不够热门。
        # 没有跨境、硬件或实体商品用途时不进入日报，也不消耗后续 DeepSeek 分析 Token。
        from app.core.logger import get_logger
        logger = get_logger("Hugging Face采集")
        logger.info(
            "Hugging Face 近期候选=%s 资格淘汰=%s 合格=%s 最终返回=%s",
            len(payload),
            rejected,
            len(results),
            min(len(results), limit),
        )
        return results[:limit]


def fetch_models(limit=15):
    return HuggingFaceCollector().collect_safe(limit)

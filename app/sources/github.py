from datetime import datetime, timedelta, timezone

import requests

from app.config import GITHUB_TOKEN
from app.sources.base import BaseCollector
from app.core.logger import get_logger
from app.relevance import attach_eligibility_metrics, report_eligibility


API = "https://api.github.com/search/repositories"

logger = get_logger("GitHub采集")

# 不再只找通用 AI/LLM 项目。加入边缘 AI、嵌入式、机器人和视觉方向，
# 让后续筛选有机会发现可直接用于硬件开发或实体商品的技术。
SEARCH_TERMS = (
    "topic:ai",
    "llm in:name,description",
    '"ai agent" in:name,description',
    '"edge ai" in:name,description',
    '"embedded ai" in:name,description',
    '"robotics ai" in:name,description',
    '"computer vision" in:name,description',
    '"on-device ai" in:name,description',
    '"amazon seller" in:name,description',
    '"shopify" ai in:name,description',
)


class GithubCollector(BaseCollector):
    name = "github"

    def collect(self, limit: int = 15):
        headers = {
            "Accept": "application/vnd.github+json",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=7)).date().isoformat()
        fetch_limit = min(max(limit * 4, 40), 60)

        candidates = {}

        for search_term in SEARCH_TERMS:
            params = {
                "q": f"{search_term} created:>={since} stars:>=5 fork:false",
                "sort": "stars",
                "order": "desc",
                "per_page": fetch_limit,
            }

            try:
                response = requests.get(
                    API,
                    headers=headers,
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()

                payload = response.json()
                if not isinstance(payload, dict):
                    logger.warning(
                        "GitHub 接口返回数据格式无效：查询=%s",
                        search_term,
                    )
                    continue

                items = payload.get("items", [])
                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("id") or item.get("html_url")
                    if key:
                        candidates[key] = item

            except Exception:
                logger.exception("GitHub 搜索失败：查询=%s", search_term)
                continue

        result = []
        rejected = 0

        for item in candidates.values():
            created_at = item.get("created_at")
            if not created_at:
                continue

            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max((now - created).total_seconds() / 3600, 1)
            except Exception:
                continue

            stars = item.get("stargazers_count", 0) or 0
            forks = item.get("forks_count", 0) or 0
            open_issues = item.get("open_issues_count", 0) or 0
            age_days = max(age_hours / 24, 0.25)
            momentum = (stars + forks * 3) / age_days

            topics = item.get("topics") or []
            description_parts = [item.get("description") or ""]
            if isinstance(topics, list) and topics:
                description_parts.append("topics: " + " ".join(str(topic) for topic in topics))

            record = {
                "source": self.name,
                "title": item.get("full_name") or item.get("name") or "",
                "url": item.get("html_url") or "",
                "description": " | ".join(part for part in description_parts if part),
                "created_at": created_at,
                "stars": stars,
                "forks": forks,
                "metrics": {
                    "stars": stars,
                    "forks": forks,
                    "open_issues": open_issues,
                    "momentum": round(momentum, 2),
                    "topics": topics if isinstance(topics, list) else [],
                    "language": item.get("language") or "",
                },
            }

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            if not eligibility["eligible"]:
                rejected += 1
                continue

            result.append(record)

        # 先看“是否真正有产品/开发价值”，再看近期增长速度；
        # 热度不能把普通 AI Demo 排到强产品机会前面。
        result.sort(
            key=lambda x: (
                float((x.get("metrics") or {}).get("opportunity_score", 0) or 0),
                float((x.get("metrics") or {}).get("momentum", 0) or 0),
                x.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "GitHub 近期候选=%s 资格淘汰=%s 合格=%s 最终返回=%s",
            len(candidates),
            rejected,
            len(result),
            min(len(result), limit),
        )
        return result[:limit]


def fetch_ai_repositories(limit: int = 15):
    return GithubCollector().collect_safe(limit)

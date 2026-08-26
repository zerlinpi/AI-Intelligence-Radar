from datetime import datetime, timedelta, timezone

import requests

from app.config import GITHUB_TOKEN
from app.sources.base import BaseCollector
from app.core.logger import get_logger


API = "https://api.github.com/search/repositories"

logger = get_logger("collector.github")


class GithubCollector(BaseCollector):
    name = "github"

    def collect(self, limit: int = 10):
        headers = {
            "Accept": "application/vnd.github+json",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=7)).date().isoformat()
        fetch_limit = min(max(limit * 5, 30), 100)

        params = {
            "q": f"topic:ai created:>={since} stars:>=5",
            "sort": "stars",
            "order": "desc",
            "per_page": fetch_limit,
        }

        response = requests.get(
            API,
            headers=headers,
            params=params,
            timeout=20,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            logger.warning("github api returned invalid payload")
            return []

        items = payload.get("items", [])
        if not isinstance(items, list):
            return []

        result = []
        for item in items:
            if not isinstance(item, dict):
                continue

            created_at = item.get("created_at")
            if not created_at:
                continue

            try:
                created = datetime.fromisoformat(
                    str(created_at).replace("Z", "+00:00")
                )
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

            result.append(
                {
                    "source": self.name,
                    "title": item.get("full_name") or item.get("name") or "",
                    "url": item.get("html_url") or "",
                    "description": item.get("description") or "",
                    "created_at": created_at,
                    "stars": stars,
                    "forks": forks,
                    "metrics": {
                        "stars": stars,
                        "forks": forks,
                        "open_issues": open_issues,
                        "momentum": round(momentum, 2),
                    },
                }
            )

        result.sort(
            key=lambda x: (x.get("metrics") or {}).get("momentum", 0),
            reverse=True,
        )
        return result[:limit]


def fetch_ai_repositories(limit: int = 10):
    return GithubCollector().collect_safe(limit)

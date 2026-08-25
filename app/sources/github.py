import requests

from app.config import GITHUB_TOKEN
from app.sources.base import BaseCollector
from app.core.logger import get_logger


API = "https://api.github.com/search/repositories"

logger = get_logger("collector.github")


class GithubCollector(BaseCollector):
    name = "github"

    def collect(self):
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        params = {
            "q": "topic:ai stars:>100",
            "sort": "stars",
            "order": "desc"
        }

        response = requests.get(
            API,
            headers=headers,
            params=params,
            timeout=20
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
        for item in items[:10]:
            if not isinstance(item, dict):
                continue

            result.append(
                {
                    "source": "github",
                    "title": item.get("name") or "",
                    "url": item.get("html_url") or "",
                    "stars": item.get("stargazers_count", 0),
                    "description": item.get("description") or ""
                }
            )

        return result


def fetch_ai_repositories():
    return GithubCollector().collect_safe()

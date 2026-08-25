import requests

from app.config import GITHUB_TOKEN
from app.sources.base import BaseCollector


API = "https://api.github.com/search/repositories"


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

        return [
            {
                "source": "github",
                "title": item.get("name"),
                "url": item.get("html_url"),
                "stars": item.get("stargazers_count", 0),
                "description": item.get("description") or ""
            }
            for item in response.json().get("items", [])[:10]
        ]


def fetch_ai_repositories():
    return GithubCollector().collect_safe()

import requests
from app.config import GITHUB_TOKEN

API = "https://api.github.com/search/repositories"


def fetch_ai_repositories():
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    params = {
        "q": "topic:ai stars:>100",
        "sort": "stars",
        "order": "desc"
    }

    response = requests.get(API, headers=headers, params=params, timeout=20)
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

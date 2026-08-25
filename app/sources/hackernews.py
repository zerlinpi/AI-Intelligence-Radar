import requests

API = "https://hacker-news.firebaseio.com/v0/topstories.json"


def fetch_hackernews(limit=10):
    ids = requests.get(API, timeout=10).json()[:limit]
    results = []
    for item_id in ids:
        item = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
            timeout=10,
        ).json()
        if item:
            results.append(item)
    return results

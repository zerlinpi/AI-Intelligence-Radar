import requests

API = "http://export.arxiv.org/api/query"


def fetch_ai_papers(limit=10):
    params = {
        "search_query": "cat:cs.AI",
        "start": 0,
        "max_results": limit,
    }
    response = requests.get(API, params=params, timeout=20)
    return response.text

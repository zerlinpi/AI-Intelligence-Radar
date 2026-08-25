import requests

API = "https://huggingface.co/api/models"


def fetch_models(limit=10):
    params = {
        "sort": "downloads",
        "direction": -1,
        "limit": limit,
    }
    response = requests.get(API, params=params, timeout=20)
    return response.json()

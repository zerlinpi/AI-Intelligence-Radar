import requests
from app.config import FEISHU_WEBHOOK


def send_feishu(message):
    if not FEISHU_WEBHOOK:
        return False

    payload = {
        "msg_type": "text",
        "content": {
            "text": message
        }
    }

    response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    response.raise_for_status()
    return True

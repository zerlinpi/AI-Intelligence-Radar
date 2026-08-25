import requests
from app.config import FEISHU_WEBHOOK


def send_feishu(message):
    if not FEISHU_WEBHOOK:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "AI Intelligence Radar Daily"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": message
                    }
                }
            ]
        }
    }

    response = requests.post(
        FEISHU_WEBHOOK,
        json=payload,
        timeout=10,
    )

    response.raise_for_status()
    return True

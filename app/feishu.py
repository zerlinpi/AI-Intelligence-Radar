import requests
from app.config import FEISHU_WEBHOOK


def send_feishu(message: str) -> bool:
    """Send AI Radar report to Feishu bot.

    Validates both HTTP status and Feishu business response code.
    """
    if not FEISHU_WEBHOOK:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "AI Intelligence Radar Daily",
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": message,
                    },
                }
            ],
        },
    }

    try:
        response = requests.post(
            FEISHU_WEBHOOK,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        if data.get("code", 0) != 0:
            return False

        return True
    except Exception:
        return False

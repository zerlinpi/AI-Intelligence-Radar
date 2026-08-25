import time

import requests

from app.config import FEISHU_WEBHOOK
from app.core.logger import get_logger


logger = get_logger("feishu")


MAX_RETRIES = 3


def send_feishu(message: str) -> bool:
    """Send AI Radar report to Feishu bot.

    Includes retry handling, timeout protection and response validation.
    Notification failure will not interrupt the radar pipeline.
    """
    if not FEISHU_WEBHOOK:
        logger.warning("feishu webhook is not configured")
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

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                FEISHU_WEBHOOK,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            if data.get("code", 0) != 0:
                raise RuntimeError(f"feishu response error: {data}")

            logger.info("feishu notification sent")
            return True

        except Exception as exc:
            logger.warning(
                "feishu send failed attempt=%s/%s error=%s",
                attempt,
                MAX_RETRIES,
                exc,
            )

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    logger.error("feishu notification failed after retries")
    return False

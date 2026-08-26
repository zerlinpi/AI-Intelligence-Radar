import time

import requests

from app.config import FEISHU_WEBHOOK
from app.core.logger import get_logger


logger = get_logger("飞书通知")


MAX_RETRIES = 3


def send_feishu(message: str) -> bool:
    """发送中文 AI 新项目雷达卡片到飞书。"""
    if not FEISHU_WEBHOOK:
        logger.warning("未配置飞书机器人地址")
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "AI 新项目雷达",
                },
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
                raise RuntimeError(f"飞书接口返回异常：{data}")

            logger.info("飞书通知发送成功")
            return True

        except Exception as exc:
            logger.warning(
                "飞书通知发送失败：第 %s/%s 次，错误=%s",
                attempt,
                MAX_RETRIES,
                exc,
            )

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    logger.error("飞书通知在重试后仍发送失败")
    return False

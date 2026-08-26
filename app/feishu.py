import time

import requests

from app.config import FEISHU_WEBHOOK
from app.core.logger import get_logger


logger = get_logger("飞书通知")


MAX_RETRIES = 3

# 这些字段是日报里最需要扫一眼就能看到的决策信息。
# 飞书消息卡片的 column_set 支持 grey 背景，因此把它们从长 Markdown 中拆成独立背景块。
HIGHLIGHT_MARKERS = (
    "**审核简报：**",
    "**重点影响产品：**",
    "**优先准备：**",
    "**影响产品：**",
    "**风险：**",
    "**准备资料：**",
)


def _markdown_element(content: str) -> dict:
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": content,
        },
    }


def _highlight_element(content: str) -> dict:
    """使用带背景色的独立块突出产品审核关键信息。"""
    text = content.strip()
    if text.startswith(">"):
        text = text[1:].strip()

    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "grey",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [_markdown_element(text)],
            }
        ],
    }


def build_card_elements(message: str) -> list:
    """把一整段日报拆成普通内容、分隔线和带背景色的高亮块。"""
    elements = []
    buffer = []

    def flush_buffer():
        if not buffer:
            return
        content = "\n".join(buffer).strip()
        buffer.clear()
        if content:
            elements.append(_markdown_element(content))

    for line in str(message or "").splitlines():
        stripped = line.strip()

        if stripped == "---":
            flush_buffer()
            elements.append({"tag": "hr"})
            continue

        if stripped.startswith(">") and any(
            marker in stripped for marker in HIGHLIGHT_MARKERS
        ):
            flush_buffer()
            elements.append(_highlight_element(stripped))
            continue

        buffer.append(line)

    flush_buffer()
    return elements or [_markdown_element(str(message or ""))]


def send_feishu(message: str) -> bool:
    """发送中文 AI 情报雷达卡片到飞书。"""
    if not FEISHU_WEBHOOK:
        logger.warning("未配置飞书机器人地址")
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "AI 新项目雷达",
                },
            },
            "elements": build_card_elements(message),
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

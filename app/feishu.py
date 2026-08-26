import random
import re
import time

import requests

from app.cards.models import CardEnvelope
from app.cards.text import payload_bytes
from app.config import (
    FEISHU_MAX_PAYLOAD_BYTES,
    FEISHU_MAX_RETRIES,
    FEISHU_SEND_TIMEOUT_SECONDS,
    FEISHU_WEBHOOK,
)
from app.core.logger import get_logger


logger = get_logger("飞书通知")


# 以下解析器只保留给旧 build_feishu_message()/send_feishu() 兼容调用。
# 正式日报已改为 Decision Model -> Card Builder -> JSON，不再依赖 Regex 猜字段。
HIGHLIGHT_MARKERS = (
    "**审核简报：**",
    "**重点影响产品：**",
    "**优先准备：**",
    "**影响产品：**",
    "**风险：**",
    "**准备资料：**",
)

LEGACY_DISPLAY_LIMITS = {
    "审核简报": 72,
    "重点影响产品": 72,
    "优先准备": 64,
    "审核要求": 72,
    "影响产品": 48,
    "风险": 56,
    "准备资料": 64,
    "建议动作": 46,
    "核心变化": 72,
    "卖家影响": 64,
    "新规要点": 72,
    "进口影响": 64,
    "产品描述": 72,
    "价值判断": 64,
    "可借鉴方向": 52,
}

LABEL_PATTERN = re.compile(r"\*\*(?P<label>[^*：]+)：\*\*")


def _clip_text(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 1)].rstrip("，。；;、 ") + "…"


def _compact_markdown_line(line: str) -> str:
    stripped = str(line or "").strip()
    match = LABEL_PATTERN.search(stripped)
    if not match:
        return line

    label = match.group("label")
    limit = LEGACY_DISPLAY_LIMITS.get(label)
    if not limit:
        return line

    prefix = stripped[: match.end()]
    body = stripped[match.end():].strip()
    if body.startswith("**") and body.endswith("**") and len(body) >= 4:
        body = body[2:-2].strip()
    return f"{prefix} {_clip_text(body, limit)}".rstrip()


def _markdown_element(content: str) -> dict:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": content},
    }


def _split_highlight_content(content: str):
    text = content.strip()
    if text.startswith(">"):
        text = text[1:].strip()
    match = LABEL_PATTERN.search(text)
    if not match:
        return "重点", text
    icon_prefix = text[: match.start()].strip()
    label_text = match.group("label")
    body = text[match.end():].strip()
    return f"{icon_prefix} **{label_text}**".strip(), body


def _highlight_element(content: str) -> dict:
    label, body = _split_highlight_content(content)
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
                "elements": [_markdown_element(label)],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 4,
                "vertical_align": "top",
                "elements": [_markdown_element(body)],
            },
        ],
    }


def build_card_elements(message: str) -> list:
    """兼容旧 Markdown 日报；新生产路径不再调用此函数。"""
    elements = []
    buffer = []

    def flush_buffer():
        if not buffer:
            return
        content = "\n".join(buffer).strip()
        buffer.clear()
        if content:
            elements.append(_markdown_element(content))

    for raw_line in str(message or "").splitlines():
        line = _compact_markdown_line(raw_line)
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


def _plain_text_payload(text: str) -> dict:
    return {
        "msg_type": "text",
        "content": {"text": str(text or "")},
    }


def _retry_sleep(attempt: int):
    delay = min(2 ** max(attempt - 1, 0), 8) + random.uniform(0, 0.35)
    time.sleep(delay)


def _post_payload(payload: dict, card_type: str) -> bool:
    """分类处理网络、429/5xx 和不可重试 4xx。"""
    for attempt in range(1, FEISHU_MAX_RETRIES + 1):
        try:
            response = requests.post(
                FEISHU_WEBHOOK,
                json=payload,
                timeout=FEISHU_SEND_TIMEOUT_SECONDS,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning(
                "飞书发送网络异常：卡片=%s 第%s/%s次 错误=%s",
                card_type,
                attempt,
                FEISHU_MAX_RETRIES,
                exc,
            )
            if attempt < FEISHU_MAX_RETRIES:
                _retry_sleep(attempt)
                continue
            return False
        except requests.RequestException as exc:
            logger.error("飞书发送请求失败：卡片=%s 错误=%s", card_type, exc)
            return False

        status = int(getattr(response, "status_code", 200) or 200)
        if status == 429 or status >= 500:
            logger.warning(
                "飞书服务暂时不可用：卡片=%s HTTP=%s 第%s/%s次",
                card_type,
                status,
                attempt,
                FEISHU_MAX_RETRIES,
            )
            if attempt < FEISHU_MAX_RETRIES:
                _retry_sleep(attempt)
                continue
            return False

        if 400 <= status < 500:
            logger.error(
                "飞书请求不可重试：卡片=%s HTTP=%s",
                card_type,
                status,
            )
            return False

        try:
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.error("飞书响应解析失败：卡片=%s 错误=%s", card_type, exc)
            return False

        if data.get("code", 0) != 0:
            logger.error("飞书业务返回异常：卡片=%s 返回=%s", card_type, data)
            return False

        logger.info(
            "飞书卡片发送成功：类型=%s Payload=%s字节",
            card_type,
            payload_bytes(payload),
        )
        return True

    return False


def send_feishu_cards(cards) -> bool:
    """按顺序发送结构化日报卡片；卡片失败时自动发送纯文本 fallback。"""
    if not FEISHU_WEBHOOK:
        logger.warning("未配置飞书机器人地址")
        return False

    all_success = True
    for raw_card in list(cards or []):
        card = raw_card if isinstance(raw_card, CardEnvelope) else CardEnvelope(**raw_card)
        size = payload_bytes(card.payload)

        if size > FEISHU_MAX_PAYLOAD_BYTES:
            logger.warning(
                "飞书卡片超过安全预算，改发纯文本：类型=%s Payload=%s字节 预算=%s字节",
                card.card_type,
                size,
                FEISHU_MAX_PAYLOAD_BYTES,
            )
            sent = _post_payload(
                _plain_text_payload(card.fallback_text),
                f"{card.card_type}:text",
            )
            all_success = all_success and sent
            continue

        sent = _post_payload(card.payload, card.card_type)
        if not sent:
            logger.warning("飞书卡片发送失败，尝试纯文本降级：类型=%s", card.card_type)
            sent = _post_payload(
                _plain_text_payload(card.fallback_text),
                f"{card.card_type}:text",
            )
        all_success = all_success and sent

    return all_success


def send_feishu(message: str) -> bool:
    """兼容旧单卡接口；正式日报请使用 send_feishu_cards。"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "turquoise",
                "title": {
                    "tag": "plain_text",
                    "content": "美国跨境经营雷达",
                },
            },
            "elements": build_card_elements(message),
        },
    }
    if not FEISHU_WEBHOOK:
        logger.warning("未配置飞书机器人地址")
        return False
    return _post_payload(payload, "legacy")

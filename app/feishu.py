import re
import time

import requests

from app.config import FEISHU_WEBHOOK
from app.core.logger import get_logger


logger = get_logger("飞书通知")


MAX_RETRIES = 3

# 飞书 raw interactive card 的 column_set 已验证支持 grey 背景。
# 关键决策信息统一用浅灰背景，不滥用高饱和色；语义通过图标与标签区分。
HIGHLIGHT_MARKERS = (
    "**审核简报：**",
    "**重点影响产品：**",
    "**优先准备：**",
    "**影响产品：**",
    "**风险：**",
    "**准备资料：**",
)

# 模型保持完整分析；这里只控制飞书最终展示预算。
# 目标：移动端 5 秒识别重点、30 秒完成主要扫读，避免单字段占据过多屏幕。
DISPLAY_LIMITS = {
    "审核简报": 72,
    "重点影响产品": 48,
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
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？；;])")
CLAUSE_SPLIT_PATTERN = re.compile(r"(?<=[，、,:：])")


def _clip_text(text: str, limit: int) -> str:
    """优先按完整句/分句压缩，最后才硬截断，避免半句话占据决策字段。"""
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value

    if limit <= 1:
        return "…"

    target = limit - 1

    def compact_by(pattern: re.Pattern) -> str:
        selected = ""
        for part in pattern.split(value):
            part = part.strip()
            if not part:
                continue
            candidate = f"{selected}{part}".strip()
            if len(candidate) > target:
                break
            selected = candidate
        return selected.rstrip("，。；;、:： ")

    # 首选完整句；若第一句本身过长，再退到逗号/顿号级分句。
    compact = compact_by(SENTENCE_SPLIT_PATTERN)
    if not compact:
        compact = compact_by(CLAUSE_SPLIT_PATTERN)

    # 完整分句过短时继续使用硬截断，避免只留下没有结论的开场短语。
    minimum_useful = min(18, max(target // 3, 8))
    if len(compact) >= minimum_useful:
        return compact + "…"

    return value[:target].rstrip("，。；;、:： ") + "…"


def _compact_markdown_line(line: str) -> str:
    """按字段语义压缩正文，不改变标题、链接和数值元信息。"""
    stripped = str(line or "").strip()
    match = LABEL_PATTERN.search(stripped)
    if not match:
        return line

    label = match.group("label")
    limit = DISPLAY_LIMITS.get(label)
    if not limit:
        return line

    body_start = match.end()
    prefix = stripped[:body_start]
    body = stripped[body_start:].strip()

    # 高亮正文不再整体加粗，只保留标签加粗，降低视觉噪音。
    if body.startswith("**") and body.endswith("**") and len(body) >= 4:
        body = body[2:-2].strip()

    compact = _clip_text(body, limit)
    return f"{prefix} {compact}" if compact else prefix


def _markdown_element(content: str) -> dict:
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": content,
        },
    }


def _split_highlight_content(content: str):
    """将高亮行拆成标签与正文，便于两列扫描。"""
    text = content.strip()
    if text.startswith(">"):
        text = text[1:].strip()

    match = LABEL_PATTERN.search(text)
    if not match:
        return "重点", text

    icon_prefix = text[: match.start()].strip()
    label_text = match.group("label")
    body = text[match.end():].strip()

    left = f"{icon_prefix} **{label_text}**".strip()
    return left, body


def _highlight_element(content: str) -> dict:
    """浅灰背景 + 1:4 标签/正文两列，保持桌面与移动端统一扫读节奏。"""
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
    """把日报拆成普通内容、分隔线和少量灰底决策块。"""
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


def send_feishu(message: str) -> bool:
    """发送中文美国跨境经营雷达卡片到飞书。"""
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
                # turquoise 仅表达日常信息层级；红/橙保留给未来独立风险告警。
                "template": "turquoise",
                "title": {
                    "tag": "plain_text",
                    "content": "美国跨境经营雷达",
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

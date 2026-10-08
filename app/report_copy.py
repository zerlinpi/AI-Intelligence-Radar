"""Presentation-only safeguards for raw scraped content.

Keep full source evidence in collectors, storage and AI prompts; this module
only controls customer-visible reports and cached-card delivery.
"""
from copy import deepcopy
import re
from typing import Iterable


_SOURCE_DUMP = re.compile(
    r"\b(?:README|MODEL_CARD|topics|language|license|pipeline_tag|"
    r"library|tags|categories)\s*:",
    flags=re.IGNORECASE,
)
_RAW_PREFIX = re.compile(
    r"^\s*(?:项目原始说明|官方原始说明)\s*[：:]",
)
_HTML_DUMP = re.compile(r"<(?:html|body|div|script|style|table|pre|code)\b", re.I)
_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_ENGLISH = re.compile(r"[A-Za-z]")
_DIRECTION_TAGS = frozenset({
    "跨境电商", "技术前沿", "硬件开发", "实体商品机会",
    "消费电子", "运动户外", "安防",
})
_UNVERIFIED = "中文摘要尚未完成核验；请查看原始来源确认实际内容。"


def is_raw_source_copy(value: str) -> bool:
    """Identify metadata dumps, pasted docs or predominantly English raw text."""
    text = str(value or "").strip()
    if not text:
        return False
    if _SOURCE_DUMP.search(text) or _RAW_PREFIX.search(text):
        return True
    if len(text) > 120 and (_HTML_DUMP.search(text) or (chr(96) * 3) in text):
        return True
    han = len(_CHINESE.findall(text))
    english = len(_ENGLISH.findall(text))
    if english > 260 and english > han * 3:
        return True
    if english > 80 and english > han * 5:
        return True
    return False


def project_display_description(
    value: str,
    *,
    tags: Iterable[str] = (),
    source_name: str = "",
) -> str:
    """Use Chinese verified analysis, never GitHub README/HF model cards."""
    text = " ".join(str(value or "").split()).strip()
    if text and not is_raw_source_copy(text) and _CHINESE.search(text):
        return text

    directions = []
    for tag in tags or ():
        tag = str(tag or "").strip()
        if tag in _DIRECTION_TAGS and tag not in directions:
            directions.append(tag)
        if len(directions) >= 2:
            break
    prefix = f"已识别方向：{'、'.join(directions)}。" if directions else ""
    source = str(source_name or "").strip().lower()
    next_step = (
        "请打开 GitHub 仓库核对实际功能、代码和维护状态。"
        if source == "github"
        else "请通过原始来源链接核对实际功能和证据。"
    )
    return prefix + "中文功能摘要尚未完成核验；" + next_step


def safe_policy_display_text(value: str) -> str:
    """Prevent untranslated raw policy feeds from being shown as legal advice."""
    text = " ".join(str(value or "").split()).strip()
    if text and not is_raw_source_copy(text) and _CHINESE.search(text):
        return text
    return "政策中文内容尚未完成核验；请通过官方原文确认适用范围、日期及要求。"


def safe_project_insight(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if is_raw_source_copy(text) or not _CHINESE.search(text):
        return _UNVERIFIED
    return text


def safe_outbound_payload(payload: dict) -> tuple[dict, bool]:
    """Sanitize cached or outbox card text without mutating persisted data."""
    if not isinstance(payload, dict):
        return payload, False
    safe = deepcopy(payload)
    changed = False

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, dict) and isinstance(text.get("content"), str):
                content = text["content"]
                if is_raw_source_copy(content):
                    text["content"] = _UNVERIFIED
                    changed = True
            if node.get("msg_type") == "text":
                body = node.get("content")
                if isinstance(body, dict) and isinstance(body.get("text"), str):
                    if is_raw_source_copy(body["text"]):
                        body["text"] = _UNVERIFIED
                        changed = True
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(safe)
    return safe, changed

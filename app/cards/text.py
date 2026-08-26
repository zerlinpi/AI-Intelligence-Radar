import json
import re
import unicodedata


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")
_CLAUSE_SPLIT = re.compile(r"(?<=[，、,:：])")


def clean_text(value) -> str:
    return " ".join(str(value or "").split())


def semantic_clip(value, limit: int) -> str:
    """优先保留完整句/分句，最后才硬截断。"""
    text = clean_text(value)
    if not text or len(text) <= limit:
        return text

    for splitter in (_SENTENCE_SPLIT, _CLAUSE_SPLIT):
        parts = [part.strip() for part in splitter.split(text) if part.strip()]
        chosen = []
        length = 0
        for part in parts:
            extra = len(part)
            if chosen and length + extra > limit:
                break
            if not chosen and extra > limit:
                break
            chosen.append(part)
            length += extra
        if chosen:
            candidate = "".join(chosen).strip()
            if candidate:
                return candidate

    return text[: max(limit - 1, 1)].rstrip("，。；;、:： ") + "…"


def display_width(text: str) -> int:
    width = 0
    for char in str(text or ""):
        east_asian = unicodedata.east_asian_width(char)
        width += 2 if east_asian in {"W", "F"} else 1
    return width


def payload_bytes(payload: dict) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )

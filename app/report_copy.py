"""Keep scraped repository documentation out of end-user report copy.

Original evidence stays on RadarItem for the relevance and AI gates; only the
presentation-facing purpose/description is replaced when it is unverified raw
source text. Never claim that a deterministic fallback translated a README.
"""
import re
from typing import Iterable


_SOURCE_DUMP = re.compile(
    r"(?:^|\s*\|\s*)(?:topics|language|license|README)\s*:|"
    r"\bREADME\s*:",
    flags=re.IGNORECASE,
)
_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_DIRECTION_TAGS = frozenset({
    "跨境电商", "技术前沿", "硬件开发", "实体商品机会",
    "消费电子", "运动户外", "安防",
})


def project_display_description(
    value: str,
    *,
    tags: Iterable[str] = (),
    source_name: str = "",
) -> str:
    """Return verified concise Chinese copy, or an explicit Chinese no-summary notice.

    Markdown/README, scraped GitHub metadata and untranslated English must
    never be presented as an AI-generated explanation. Do not mutate evidence.
    Legitimate Chinese analysis is preserved, including the content-paging
    invariants used by Feishu cards.
    """
    text = " ".join(str(value or "").split()).strip()
    if text and not _SOURCE_DUMP.search(text) and _CHINESE.search(text):
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

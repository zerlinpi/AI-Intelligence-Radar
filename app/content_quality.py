import re
from difflib import SequenceMatcher
from typing import Iterable


_MARKDOWN_RE = re.compile(r"[`*_>#\[\](){}|]+")
_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])|\n+")


def normalize_copy(value: str) -> str:
    """用于相似度比较的轻量规范化；不修改最终展示原文。"""
    text = str(value or "").lower()
    text = _MARKDOWN_RE.sub(" ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _char_ngrams(text: str, size: int = 3) -> set:
    compact = normalize_copy(text).replace(" ", "")
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[i:i + size] for i in range(len(compact) - size + 1)}


def copy_similarity(left: str, right: str) -> float:
    """返回 0-1 的文本相似度，兼顾中英文和长短句包含关系。"""
    left_norm = normalize_copy(left)
    right_norm = normalize_copy(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_grams = _char_ngrams(left_norm)
    right_grams = _char_ngrams(right_norm)
    if not left_grams or not right_grams:
        return SequenceMatcher(None, left_norm, right_norm).ratio()

    overlap = len(left_grams & right_grams)
    containment = overlap / max(min(len(left_grams), len(right_grams)), 1)
    jaccard = overlap / max(len(left_grams | right_grams), 1)
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(jaccard, containment * 0.92, sequence * 0.9)


def is_redundant_copy(candidate: str, references: Iterable[str], threshold: float = 0.78) -> bool:
    text = str(candidate or "").strip()
    if not text:
        return True
    return any(
        copy_similarity(text, reference) >= threshold
        for reference in references
        if str(reference or "").strip()
    )


def distinct_sentences(candidate: str, references: Iterable[str], threshold: float = 0.78) -> str:
    """删除只是在复述前文的句子，保留所有具有新增信息的句子。

    若整段都被判断为重复，则返回空字符串，由调用方决定是否保留原文或省略该字段。
    """
    value = " ".join(str(candidate or "").split()).strip()
    if not value:
        return ""

    refs = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    if not refs:
        return value

    parts = [part.strip() for part in _SENTENCE_RE.split(value) if part.strip()]
    if len(parts) <= 1:
        return "" if is_redundant_copy(value, refs, threshold) else value

    kept = []
    evolving_refs = list(refs)
    for part in parts:
        if is_redundant_copy(part, evolving_refs, threshold):
            continue
        kept.append(part)
        evolving_refs.append(part)
    return "".join(kept).strip()

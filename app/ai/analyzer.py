import json
import re
from typing import Dict, List

from app.ai.client import (
    call_llm_with_retry,
    get_llm_client,
    get_llm_model,
)
from app.config import LLM_API_KEY, LLM_MAX_TOKENS, LLM_TEMPERATURE
from app.core.logger import get_logger


logger = get_logger("AI分析")

MAX_DESCRIPTION_CHARS = 240
MAX_TITLE_CHARS = 120
MAX_BATCH_ITEMS = 10
MAX_OUTPUT_TOKENS = 700

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
}

OPPORTUNITY_MAP = {
    "高": "high",
    "中": "medium",
    "低": "low",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

METRIC_KEYS = (
    "stars",
    "forks",
    "upvotes",
    "comments",
    "downloads",
    "likes",
    "momentum",
)


def _fallback_result(item: Dict, reason: str = "") -> Dict:
    if reason:
        logger.warning("AI 分析降级：%s", reason)

    return {
        "summary": "AI 分析暂不可用，建议直接查看项目页面了解最新进展。",
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": reason,
        },
    }


def _compact_metrics(item: Dict) -> Dict:
    metrics = item.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    result = {}
    for key in METRIC_KEYS:
        value = metrics.get(key, item.get(key))
        if value not in (None, "", 0, 0.0):
            result[key] = value

    return result


def _compact_item(item: Dict, index: int) -> Dict:
    title = str(item.get("title") or "")[:MAX_TITLE_CHARS]
    description = " ".join(str(item.get("description") or "").split())
    description = description[:MAX_DESCRIPTION_CHARS]

    return {
        "序号": index,
        "名称": title,
        "简介": description,
        "来源": SOURCE_NAMES.get(str(item.get("source") or ""), str(item.get("source") or "")),
        "热度": round(float(item.get("trend_score") or 0), 1),
        "指标": _compact_metrics(item),
    }


def _extract_json_object(content: str) -> Dict:
    if not content:
        return {}

    text = content.strip()
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group(0))
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}


def _normalize_batch_result(raw: Dict, items: List[Dict], meta: Dict) -> List[Dict]:
    rows = raw.get("结果") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return [_fallback_result(item, "模型返回格式无效") for item in items]

    by_index = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("序号"))
        except (TypeError, ValueError):
            continue
        by_index[index] = row

    results = []
    for index, item in enumerate(items, start=1):
        row = by_index.get(index)
        if not row:
            results.append(_fallback_result(item, f"缺少第 {index} 条分析结果"))
            continue

        try:
            business_score = float(row.get("商业分", 50) or 50)
        except (TypeError, ValueError):
            business_score = 50
        business_score = round(min(max(business_score, 0), 100), 2)

        opportunity = OPPORTUNITY_MAP.get(
            str(row.get("机会") or "中").strip().lower(),
            "medium",
        )
        summary = str(row.get("摘要") or "").strip()
        idea = str(row.get("建议") or "").strip()

        results.append(
            {
                "summary": summary or "暂无 AI 分析摘要。",
                "business_score": business_score,
                "opportunity": opportunity,
                "startup_ideas": [idea] if idea else [],
                "llm_meta": meta,
            }
        )

    return results


def analyze_items(items: List[Dict]) -> List[Dict]:
    """一次请求批量分析最多 10 个项目，减少重复提示词和连接开销。"""
    items = list(items or [])[:MAX_BATCH_ITEMS]
    if not items:
        return []

    if not LLM_API_KEY:
        return [_fallback_result(item, "缺少 LLM API 密钥") for item in items]

    compact_items = [
        _compact_item(item, index)
        for index, item in enumerate(items, start=1)
    ]
    compact_json = json.dumps(
        compact_items,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    prompt = (
        "你是早期AI项目分析师。只依据项目简介、上线热度和早期指标判断，"
        "不要因历史规模或品牌知名度加分。"
        "请用简体中文分析每项，摘要不超过45字，建议不超过25字。"
        "仅返回JSON，不要解释。格式："
        '{"结果":[{"序号":1,"摘要":"...","商业分":0,"机会":"高|中|低","建议":"..."}]}。'
        f"项目：{compact_json}"
    )

    output_tokens = min(max(int(LLM_MAX_TOKENS or 1), 1), MAX_OUTPUT_TOKENS)

    client = get_llm_client()
    response, meta = call_llm_with_retry(
        lambda: client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            max_tokens=output_tokens,
        )
    )

    if not meta.get("success") or response is None:
        reason = meta.get("error", "模型请求失败")
        return [_fallback_result(item, reason) for item in items]

    try:
        content = response.choices[0].message.content
        parsed = _extract_json_object(content)
        results = _normalize_batch_result(parsed, items, meta)

        usage = meta.get("usage") or {}
        logger.info(
            "AI 批量分析完成：项目=%s 输入Token=%s 输出Token=%s 总Token=%s",
            len(items),
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0),
        )
        return results
    except Exception as exc:
        return [_fallback_result(item, f"解析模型结果失败：{exc}") for item in items]


def analyze_item(item: Dict) -> Dict:
    """兼容旧调用；单项分析仍复用批量逻辑。"""
    results = analyze_items([item])
    return results[0] if results else _fallback_result(item, "没有可分析项目")

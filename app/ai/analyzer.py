import json
import re
from datetime import datetime, timezone
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

METRIC_LABELS = {
    "stars": "星",
    "forks": "分",
    "upvotes": "票",
    "comments": "评",
    "downloads": "下",
    "likes": "赞",
    "momentum": "势",
}


def _local_trend_score(item: Dict) -> float:
    try:
        return round(float(item.get("trend_score", 50) or 50), 2)
    except (TypeError, ValueError):
        return 50


def _fallback_result(item: Dict, reason: str = "") -> Dict:
    if reason:
        logger.warning("AI 分析降级：%s", reason)

    return {
        "summary": "AI 分析暂不可用，建议直接查看项目页面了解最新进展。",
        "trend_score": _local_trend_score(item),
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": reason,
        },
    }


def _compact_metrics(item: Dict) -> str:
    metrics = item.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    parts = []
    for key, label in METRIC_LABELS.items():
        value = metrics.get(key, item.get(key))
        if value not in (None, "", 0, 0.0):
            parts.append(f"{label}={value}")

    return ";".join(parts)


def _age_hours(item: Dict):
    created_at = item.get("created_at")
    if not created_at:
        return None

    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(round((datetime.now(timezone.utc) - created).total_seconds() / 3600), 0)
    except Exception:
        return None


def _compact_item(item: Dict, index: int) -> list:
    title = str(item.get("title") or "")[:MAX_TITLE_CHARS]
    description = " ".join(str(item.get("description") or "").split())
    description = description[:MAX_DESCRIPTION_CHARS]
    source = str(item.get("source") or "")

    # 顺序固定为：序号、名称、简介、来源、上线小时、热度、指标。
    return [
        index,
        title,
        description,
        SOURCE_NAMES.get(source, source),
        _age_hours(item),
        round(float(item.get("trend_score") or 0), 1),
        _compact_metrics(item),
    ]


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


def _read_result_row(row):
    """读取紧凑数组格式，同时兼容旧字典格式。"""
    if isinstance(row, list) and len(row) >= 5:
        return {
            "序号": row[0],
            "摘要": row[1],
            "商业分": row[2],
            "机会": row[3],
            "建议": row[4],
        }

    if isinstance(row, dict):
        return row

    return None


def _normalize_batch_result(raw: Dict, items: List[Dict], meta: Dict) -> List[Dict]:
    rows = raw.get("结果") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return [_fallback_result(item, "模型返回格式无效") for item in items]

    by_index = {}
    for raw_row in rows:
        row = _read_result_row(raw_row)
        if not row:
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
                "trend_score": _local_trend_score(item),
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
        "你是早期AI项目分析师。项目数组每项依次为"
        "[序号,名称,简介,来源,上线小时,热度,指标]。"
        "只看早期价值，不因历史规模或品牌加分。"
        "每项用简体中文：摘要≤45字，建议≤25字。"
        "只返回JSON："
        '{"结果":[[序号,"摘要",商业分,"高|中|低","建议"]]}。'
        f"项目={compact_json}"
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

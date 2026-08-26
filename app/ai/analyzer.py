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

MAX_DESCRIPTION_CHARS = 220
MAX_TITLE_CHARS = 120
MAX_BATCH_ITEMS = 13
MAX_OUTPUT_TOKENS = 900

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
    "amazon_policy": "Amazon",
    "tiktok_policy": "TikTok Shop",
    "us_regulation": "美国跨境法规",
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
    "policy_score": "政",
}


def _local_trend_score(item: Dict) -> float:
    try:
        return round(float(item.get("trend_score", 50) or 50), 2)
    except (TypeError, ValueError):
        return 50


def _is_policy(item: Dict) -> bool:
    return str(item.get("category") or "").lower() == "policy"


def _fallback_result(item: Dict, reason: str = "") -> Dict:
    if reason:
        logger.warning("AI 分析降级：%s", reason)

    if _is_policy(item):
        return {
            "purpose": "政策内容暂无法生成，请查看官方原文。",
            "summary": "影响判断暂不可用，建议优先查看原始政策。",
            "trend_score": 0,
            "business_score": 50,
            "opportunity": "medium",
            "startup_ideas": ["查看官方原文并核对适用范围"],
            "llm_meta": {
                "success": False,
                "fallback": True,
                "reason": reason,
            },
        }

    return {
        "purpose": "项目用途暂无法生成，请查看项目原始说明。",
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

    tags = metrics.get("priority_tags") or []
    if isinstance(tags, list) and tags:
        parts.append("标=" + "/".join(str(tag) for tag in tags[:2]))

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
    item_type = "政" if _is_policy(item) else "项"

    # 顺序固定：序号、类型、名称、简介、来源、时间小时、热度、指标。
    return [
        index,
        item_type,
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
    """读取紧凑数组格式，同时兼容旧数组和字典格式。"""
    if isinstance(row, list) and len(row) >= 6:
        return {
            "序号": row[0],
            "用途": row[1],
            "摘要": row[2],
            "商业分": row[3],
            "机会": row[4],
            "建议": row[5],
        }

    if isinstance(row, list) and len(row) >= 5:
        return {
            "序号": row[0],
            "用途": "",
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
        purpose = str(row.get("用途") or "").strip()
        summary = str(row.get("摘要") or "").strip()
        idea = str(row.get("建议") or "").strip()

        results.append(
            {
                "purpose": purpose or (
                    "政策内容暂不明确，请查看官方原文。"
                    if _is_policy(item)
                    else "项目用途暂不明确，请查看项目说明。"
                ),
                "summary": summary or "暂无 AI 分析摘要。",
                "trend_score": 0 if _is_policy(item) else _local_trend_score(item),
                "business_score": business_score,
                "opportunity": opportunity,
                "startup_ideas": [idea] if idea else [],
                "llm_meta": meta,
            }
        )

    return results


def analyze_items(items: List[Dict]) -> List[Dict]:
    """一次请求同时分析政策与项目，避免增加第二次 DeepSeek 调用。"""
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
        "你是跨境电商经营风险与早期AI产品机会分析师。数组每项依次为"
        "[序号,类型(政/项),名称,简介,来源,时间小时,热度,指标]。"
        "若类型=政：用途字段用≤36字概括新政策/规则，必须保留明确日期、阈值或限制；"
        "摘要≤36字说明对跨境卖家的直接影响；分数代表影响程度0-100；高中低代表处理紧急度；"
        "建议≤24字给出最具体的下一步动作。"
        "若类型=项：重点判断Amazon、Shopify、TikTok Shop、独立站、选品、Listing、广告、"
        "本地化、客服、SEO、竞品、定价、物流、库存、评论、达人营销，以及是否可做成SaaS、"
        "Agent、插件、API或自动化产品；用途≤28字，摘要≤32字，建议≤22字。"
        "不要因历史规模或品牌知名度加分。只返回JSON："
        '{"结果":[[序号,"用途","判断",分数,"高|中|低","建议"]]}。'
        f"数据={compact_json}"
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
            "AI 批量分析完成：条目=%s 输入Token=%s 输出Token=%s 总Token=%s",
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
    return results[0] if results else _fallback_result(item, "没有可分析条目")

import logging
from typing import Dict

from app.ai.client import (
    call_llm_with_retry,
    get_llm_client,
    get_llm_model,
)
from app.ai.parser import parse_json_response
from app.config import LLM_API_KEY, LLM_MAX_TOKENS, LLM_TEMPERATURE


logger = logging.getLogger(__name__)


def _fallback_result(item: Dict, reason: str = "") -> Dict:
    if reason:
        logger.warning("LLM fallback used: %s", reason)

    return {
        "summary": "AI 分析暂不可用，建议直接查看项目页面了解最新进展。",
        "trend_score": item.get("trend_score", 50),
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": reason,
        },
    }


def analyze_item(item: Dict) -> Dict:
    if not LLM_API_KEY:
        return _fallback_result(item, "missing llm api key")

    client = get_llm_client()
    metrics = item.get("metrics", {})

    prompt = f"""
你是一名专注于早期 AI 产品与开源项目的创业分析师。

请判断这个项目为什么正在早期升温，它解决什么问题，技术或产品价值是什么，以及是否存在商业机会。
重点关注“刚上线后的增长速度”，不要因为历史累计 stars、下载量或品牌知名度而高估成熟项目。

项目名称：{item.get('title')}
项目简介：{item.get('description')}
来源：{item.get('source')}
早期指标：{metrics}
新项目热度分：{item.get('trend_score', 0)}

请只返回合法 JSON，不要使用 Markdown。
所有面向用户展示的文本必须使用简体中文。

返回结构：
{{
  "summary": "用 1-2 句话说明项目是什么、为什么值得现在关注",
  "trend_score": 0,
  "business_score": 0,
  "opportunity": "high|medium|low",
  "startup_ideas": ["中文机会点"]
}}
"""

    response, meta = call_llm_with_retry(
        lambda: client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )
    )

    if not meta.get("success") or response is None:
        return _fallback_result(item, meta.get("error", "unknown error"))

    try:
        result = parse_json_response(
            response.choices[0].message.content
        )
        result["llm_meta"] = meta
        return result
    except Exception as exc:
        return _fallback_result(item, str(exc))

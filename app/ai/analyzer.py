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
        "summary": (item.get("description") or "")[:300],
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

    prompt = f"""
Analyze this project as an AI startup analyst.

Title: {item.get('title')}
Description: {item.get('description')}
Source: {item.get('source')}

Return JSON only:
{{
"summary":"",
"trend_score":0,
"business_score":0,
"opportunity":"high|medium|low",
"startup_ideas":[]
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

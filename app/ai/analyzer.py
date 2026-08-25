import json
from typing import Dict

from app.ai.client import get_llm_client, get_llm_model
from app.ai.parser import parse_json_response
from app.config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_API_KEY


def analyze_item(item: Dict) -> Dict:
    if not LLM_API_KEY:
        return {
            "summary": (item.get("description") or "")[:300],
            "trend_score": 50,
            "business_score": 50,
            "opportunity": "medium",
        }

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

    try:
        response = client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )

        return parse_json_response(
            response.choices[0].message.content
        )

    except Exception:
        return {
            "summary": (item.get("description") or "")[:300],
            "trend_score": 50,
            "business_score": 50,
            "opportunity": "medium",
        }

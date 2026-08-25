import json
from typing import Dict

from openai import OpenAI

from app.config import OPENAI_API_KEY, LLM_MODEL


def analyze_item(item: Dict) -> Dict:
    if not OPENAI_API_KEY:
        return {
            "summary": (item.get("description") or "")[:300],
            "trend_score": 50,
            "business_score": 50,
            "opportunity": "medium",
        }

    client = OpenAI(api_key=OPENAI_API_KEY)

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

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return json.loads(response.choices[0].message.content)

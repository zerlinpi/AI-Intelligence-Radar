import json
import re
from typing import Dict


DEFAULT_ANALYSIS = {
    "summary": "",
    "trend_score": 0,
    "business_score": 0,
    "opportunity": "medium",
    "startup_ideas": [],
}


def parse_json_response(content: str) -> Dict:
    """Parse JSON returned by LLM with markdown/fallback handling.

    LLM responses are not guaranteed to be strict JSON. This parser
    removes markdown fences, extracts JSON objects when possible, and
    guarantees required analysis fields exist.
    """
    if not content:
        return DEFAULT_ANALYSIS.copy()

    text = content.strip()

    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    result = None

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                result = None

    if not isinstance(result, dict):
        return DEFAULT_ANALYSIS.copy()

    output = DEFAULT_ANALYSIS.copy()
    output.update(result)

    if not isinstance(output.get("startup_ideas"), list):
        output["startup_ideas"] = []

    return output

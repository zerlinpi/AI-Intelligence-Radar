import json
import re
from typing import Dict


def parse_json_response(content: str) -> Dict:
    """Parse JSON returned by LLM with markdown/fallback handling."""
    if not content:
        return {}

    text = content.strip()

    text = re.sub(r"```(?:json)?", "", text)
    text = text.replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    return {}

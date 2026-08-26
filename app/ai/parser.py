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

VALID_OPPORTUNITIES = {"high", "medium", "low"}


def _default_analysis() -> Dict:
    result = DEFAULT_ANALYSIS.copy()
    result["startup_ideas"] = []
    return result


def _bounded_score(value) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0

    return round(min(max(number, 0), 100), 2)


def parse_json_response(content: str) -> Dict:
    """Parse and normalize JSON returned by the configured LLM.

    LLM responses are not guaranteed to be strict JSON. This parser removes
    markdown fences, extracts JSON objects when possible, and guarantees that
    fields written to SQLite or shown in Feishu use stable types.
    """
    if not content:
        return _default_analysis()

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
        return _default_analysis()

    output = _default_analysis()
    output.update(result)

    summary = output.get("summary")
    output["summary"] = summary.strip() if isinstance(summary, str) else str(summary or "")

    output["trend_score"] = _bounded_score(output.get("trend_score"))
    output["business_score"] = _bounded_score(output.get("business_score"))

    opportunity = str(output.get("opportunity") or "medium").lower().strip()
    output["opportunity"] = (
        opportunity if opportunity in VALID_OPPORTUNITIES else "medium"
    )

    ideas = output.get("startup_ideas")
    if not isinstance(ideas, list):
        ideas = []
    output["startup_ideas"] = [
        str(idea).strip()
        for idea in ideas
        if str(idea).strip()
    ]

    return output

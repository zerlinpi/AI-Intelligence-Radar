from typing import Dict


def analyze_item(item: Dict) -> Dict:
    """LLM analysis placeholder.
    Replace with OpenAI API integration in production.
    """
    description = item.get("description", "") or ""

    return {
        "summary": description[:300],
        "business_score": 50,
        "opportunity": "medium"
    }

from datetime import datetime

from app.scoring import calculate_opportunity_score


def run_daily_radar():
    return {
        "time": datetime.utcnow().isoformat(),
        "sources": [
            "github",
            "producthunt",
            "hackernews",
            "arxiv",
            "huggingface"
        ],
        "score": calculate_opportunity_score({})
    }

from datetime import datetime

from app.cleaner import normalize_items
from app.scoring import calculate_score
from app.ai.analyzer import analyze_item
from app.feishu import send_feishu

from app.sources.github import fetch_ai_repositories
from app.sources.hackernews import fetch_hackernews
from app.sources.huggingface import fetch_models

from app.database.session import SessionLocal, init_database
from app.storage.repository import save_batch


def collect_sources():
    items = []

    collectors = [
        fetch_ai_repositories,
        fetch_hackernews,
        fetch_models,
    ]

    for collector in collectors:
        try:
            data = collector()
            if isinstance(data, list):
                items.extend(data)
        except Exception as error:
            print(f"collector failed: {collector.__name__}: {error}")

    return items


def build_report(items):
    analyzed = []

    for item in items[:50]:
        item["trend_score"] = calculate_score(item)

        try:
            item["analysis"] = analyze_item(item)
        except Exception as error:
            item["analysis"] = {
                "summary": "Analysis unavailable",
                "error": str(error),
            }

        analyzed.append(item)

    analyzed.sort(
        key=lambda x: x.get("trend_score", 0),
        reverse=True,
    )

    return analyzed[:10]


def run_daily_radar():
    init_database()

    raw_items = collect_sources()
    cleaned_items = normalize_items(raw_items)
    report = build_report(cleaned_items)

    db = SessionLocal()
    try:
        save_batch(db, report)
    finally:
        db.close()

    message = "🔥 AI Intelligence Radar Daily\n\n"

    for index, item in enumerate(report, start=1):
        analysis = item.get("analysis", {})
        message += (
            f"{index}. {item.get('title', 'Unknown')}\n"
            f"Source: {item.get('source', 'unknown')}\n"
            f"Trend Score: {item.get('trend_score', 0)}\n"
            f"{analysis.get('summary', item.get('description', '')[:120])}\n\n"
        )

    send_feishu(message)

    return {
        "time": datetime.utcnow().isoformat(),
        "items": report,
    }

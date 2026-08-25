from datetime import datetime
import time
import uuid

from app.cleaner import normalize_items
from app.scoring import calculate_score
from app.ai.analyzer import analyze_item
from app.feishu import send_feishu
from app.core.logger import get_logger
from app.models.radar_item import RadarItem

from app.sources.github import GithubCollector
from app.sources.hackernews import HackerNewsCollector
from app.sources.huggingface import HuggingFaceCollector
from app.sources.arxiv import ArxivCollector
from app.sources.producthunt import ProductHuntCollector

from app.database.session import SessionLocal, init_database
from app.storage.repository import save_batch, exists


logger = get_logger("pipeline")

MAX_ANALYSIS_ITEMS = 50
MAX_REPORT_ITEMS = 10

COLLECTORS = [
    GithubCollector(),
    HackerNewsCollector(),
    HuggingFaceCollector(),
    ArxivCollector(),
    ProductHuntCollector(),
]


def collect_sources():
    """Collect all sources. A failed collector must not stop the pipeline."""
    items = []

    for collector in COLLECTORS:
        start = time.time()
        try:
            data = collector.collect_safe()
            if not isinstance(data, list):
                data = []

            for raw_item in data:
                if isinstance(raw_item, RadarItem):
                    items.append(raw_item)
                elif isinstance(raw_item, dict):
                    items.append(RadarItem.from_dict(raw_item))

            logger.info(
                "collector=%s items=%s duration=%.2fs",
                collector.__class__.__name__,
                len(data),
                time.time() - start,
            )

        except Exception:
            logger.exception(
                "collector failed=%s duration=%.2fs",
                collector.__class__.__name__,
                time.time() - start,
            )

    return items


def fallback_analysis(item, error=None):
    return {
        "summary": item.description[:300],
        "trend_score": item.trend_score or 50,
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "error": str(error) if error else None,
    }


def build_report(items):
    analyzed = []

    for item in items[:MAX_ANALYSIS_ITEMS]:
        item.trend_score = calculate_score(item.to_dict())

        try:
            item.analysis = analyze_item(item.to_dict())
        except Exception as error:
            logger.exception("analysis failed item=%s", item.title)
            item.analysis = fallback_analysis(item, error)

        analyzed.append(item)

    analyzed.sort(key=lambda x: x.trend_score, reverse=True)
    return analyzed[:MAX_REPORT_ITEMS]


def filter_existing_items(db, items):
    return [item for item in items if not item.url or not exists(db, item.url)]


def build_feishu_message(items):
    message = "🔥 AI Intelligence Radar Daily\n\n"

    for index, item in enumerate(items, start=1):
        message += (
            f"{index}. {item.title}\n"
            f"Source: {item.source}\n"
            f"Trend Score: {item.trend_score}\n"
            f"Business Opportunity: {item.analysis.get('opportunity', 'medium')}\n"
            f"{item.analysis.get('summary', item.description[:120])}\n\n"
        )

    return message


def run_daily_radar():
    execution_id = str(uuid.uuid4())
    started = time.time()

    logger.info("daily radar started execution_id=%s", execution_id)

    init_database()

    items = collect_sources()
    cleaned = normalize_items([item.to_dict() for item in items])
    radar_items = [RadarItem.from_dict(item) for item in cleaned]

    db = SessionLocal()
    report = []

    try:
        new_items = filter_existing_items(db, radar_items)
        report = build_report(new_items)
        save_batch(db, [item.to_dict() for item in report])
        logger.info("saved=%s execution_id=%s", len(report), execution_id)
    except Exception:
        logger.exception("pipeline database stage failed execution_id=%s", execution_id)
    finally:
        db.close()

    if report:
        try:
            send_feishu(build_feishu_message(report))
            logger.info("feishu sent execution_id=%s", execution_id)
        except Exception:
            logger.exception("feishu failed execution_id=%s", execution_id)

    duration = round(time.time() - started, 2)
    logger.info(
        "daily radar finished execution_id=%s duration=%ss items=%s",
        execution_id,
        duration,
        len(report),
    )

    return {
        "execution_id": execution_id,
        "time": datetime.utcnow().isoformat(),
        "duration": duration,
        "items": [item.to_dict() for item in report],
    }

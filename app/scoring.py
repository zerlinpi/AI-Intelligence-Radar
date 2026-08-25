from datetime import datetime, timezone


def _normalize(value, divisor, weight):
    """Normalize a metric into a weighted 0-100 radar component."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0

    return min(value / divisor * weight, weight)


def freshness_score(item):
    """Calculate freshness signal from created timestamps."""
    created_at = item.get("created_at")

    if not created_at:
        return 0

    try:
        created = datetime.fromisoformat(
            str(created_at).replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        hours = max((now - created).total_seconds() / 3600, 0)

        if hours <= 24:
            return 15
        if hours <= 72:
            return 10
        if hours <= 168:
            return 5
    except Exception:
        pass

    return 0


def calculate_score(item):
    """
    Calculate AI Intelligence Radar score.

    Weighting:
    - Community momentum: 30
    - Developer activity: 20
    - AI relevance: 20
    - Market signal: 15
    - Freshness: 15
    """

    community = (
        _normalize(item.get("stars"), 1000, 20)
        + _normalize(item.get("upvotes"), 100, 10)
    )

    developer_activity = (
        _normalize(item.get("forks"), 100, 10)
        + _normalize(item.get("comments"), 50, 10)
    )

    ai_relevance = item.get("ai_relevance_score", 0) or 0
    ai_relevance = min(float(ai_relevance) * 0.20, 20)

    market_signal = (
        _normalize(item.get("downloads"), 10000, 10)
        + _normalize(item.get("business_interest"), 100, 5)
    )

    freshness = freshness_score(item)

    score = (
        community
        + developer_activity
        + ai_relevance
        + market_signal
        + freshness
    )

    return round(min(score, 100), 2)

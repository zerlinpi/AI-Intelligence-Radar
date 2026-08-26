from datetime import datetime, timezone


def _normalize(value, divisor, weight):
    """Normalize a metric into a weighted score component."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0

    if value < 0:
        value = 0

    return min(value / divisor * weight, weight)


def _metric(item, key):
    if not isinstance(item, dict):
        return 0

    if key in item:
        return item.get(key) or 0

    metrics = item.get("metrics") or {}
    if isinstance(metrics, dict):
        return metrics.get(key) or 0

    return 0


def age_hours(item):
    """Return item age in hours, or None when creation time is unavailable."""
    created_at = item.get("created_at") if isinstance(item, dict) else None
    if not created_at:
        return None

    try:
        created = datetime.fromisoformat(
            str(created_at).replace("Z", "+00:00")
        )
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return max(
            (datetime.now(timezone.utc) - created).total_seconds() / 3600,
            0,
        )
    except Exception:
        return None


def freshness_score(item):
    """Strongly reward projects launched recently."""
    hours = age_hours(item)
    if hours is None:
        return 0

    if hours <= 6:
        return 40
    if hours <= 24:
        return 36
    if hours <= 72:
        return 30
    if hours <= 168:
        return 22
    if hours <= 336:
        return 10

    return 0


def calculate_score(item):
    """
    Calculate early-stage project heat score.

    This score intentionally favors newly launched projects that are gaining
    attention quickly instead of mature projects with large lifetime totals.

    Weighting:
    - Freshness: 40
    - Community growth velocity: 35
    - Early engagement: 15
    - Source momentum signal: 10
    """
    if not isinstance(item, dict):
        return 0

    hours = age_hours(item)
    age_days = max((hours or 24) / 24, 0.25)

    stars_per_day = float(_metric(item, "stars") or 0) / age_days
    upvotes_per_day = float(_metric(item, "upvotes") or 0) / age_days
    downloads_per_day = float(_metric(item, "downloads") or 0) / age_days
    forks_per_day = float(_metric(item, "forks") or 0) / age_days
    comments_per_day = float(_metric(item, "comments") or 0) / age_days
    likes_per_day = float(_metric(item, "likes") or 0) / age_days

    community_velocity = (
        _normalize(stars_per_day, 150, 20)
        + _normalize(upvotes_per_day, 80, 10)
        + _normalize(downloads_per_day, 10000, 5)
    )

    engagement = (
        _normalize(forks_per_day, 30, 5)
        + _normalize(comments_per_day, 25, 5)
        + _normalize(likes_per_day, 30, 5)
    )

    source_momentum = _normalize(_metric(item, "momentum"), 5000, 10)

    score = (
        freshness_score(item)
        + community_velocity
        + engagement
        + source_momentum
    )

    return round(min(max(score, 0), 100), 2)

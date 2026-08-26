from datetime import datetime, timezone
import re


CROSS_BORDER_KEYWORDS = (
    "ecommerce",
    "e-commerce",
    "shopify",
    "amazon",
    "etsy",
    "walmart",
    "tiktok shop",
    "seller",
    "merchant",
    "storefront",
    "product listing",
    "listing optimization",
    "cross-border",
    "cross border",
    "dropshipping",
    "fulfillment",
    "inventory",
    "warehouse",
    "shipping",
    "logistics",
    "returns",
    "customer support",
    "customer service",
    "localization",
    "translation",
    "product research",
    "market research",
    "competitor research",
    "keyword research",
    "pricing",
    "price tracking",
    "advertising",
    "ad creative",
    "meta ads",
    "google ads",
    "seo",
    "affiliate",
    "influencer",
    "ugc",
    "review analysis",
    "reviews",
    "sourcing",
    "procurement",
)

PRODUCTIZABLE_KEYWORDS = (
    "saas",
    "platform",
    "tool",
    "app",
    "api",
    "sdk",
    "agent",
    "copilot",
    "assistant",
    "automation",
    "workflow",
    "dashboard",
    "browser",
    "extension",
    "plugin",
    "integration",
    "crm",
    "analytics",
    "generator",
    "monitor",
    "search",
    "scraper",
    "service",
)


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


def _search_text(item) -> str:
    if not isinstance(item, dict):
        return ""

    parts = [
        item.get("title"),
        item.get("description"),
        item.get("category"),
        item.get("source"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    """单词型关键词按词边界匹配，避免 research 命中 search 等误判。"""
    keyword = keyword.lower().strip()

    if re.fullmatch(r"[a-z0-9]+", keyword):
        pattern = rf"\b{re.escape(keyword)}(?:s|es)?\b"
        return bool(re.search(pattern, text))

    return keyword in text


def priority_tags(item):
    """识别跨境电商相关性与产品化潜力，仅用于选品优先级。"""
    text = _search_text(item)
    tags = []

    if any(_contains_keyword(text, keyword) for keyword in CROSS_BORDER_KEYWORDS):
        tags.append("跨境电商")

    source = str(item.get("source") or "").lower() if isinstance(item, dict) else ""
    product_signal = any(
        _contains_keyword(text, keyword)
        for keyword in PRODUCTIZABLE_KEYWORDS
    )

    if source == "producthunt" or product_signal:
        tags.append("可产品化")

    return tags


def calculate_priority_score(item):
    """计算业务选品优先分，不改变原有早期热度分语义。

    - 跨境电商直接相关：+20
    - 具备 SaaS / 工具 / Agent / API 等产品化形态：+10
    """
    tags = priority_tags(item)
    score = 0

    if "跨境电商" in tags:
        score += 20
    if "可产品化" in tags:
        score += 10

    return score


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

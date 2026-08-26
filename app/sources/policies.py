from datetime import datetime, timedelta, timezone
import html
import re
from urllib.parse import quote_plus

import feedparser
import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


logger = get_logger("政策采集")

MAX_POLICY_AGE_DAYS = 30

# 通过 Google News RSS 发现公开页面，但查询严格限定到官方域名。
POLICY_QUERIES = (
    {
        "source": "amazon_policy",
        "source_name": "Amazon",
        "kind": "平台政策",
        "weight": 30,
        "query": (
            'site:sellercentral.amazon.com/seller-forums/discussions '
            'News_Amazon (update OR requirement OR policy OR effective OR enforcement)'
        ),
    },
    {
        "source": "amazon_policy",
        "source_name": "Amazon",
        "kind": "平台政策",
        "weight": 26,
        "query": 'site:sell.amazon.com/blog/announcements Amazon seller update',
    },
    {
        "source": "tiktok_policy",
        "source_name": "TikTok Shop",
        "kind": "平台政策",
        "weight": 28,
        "query": 'site:seller-us.tiktok.com/university "Policy Pulse" TikTok Shop',
    },
    {
        "source": "us_regulation",
        "source_name": "美国跨境法规",
        "kind": "跨境法规",
        "weight": 22,
        "query": (
            'site:cbp.gov (ecommerce OR e-commerce OR import OR de minimis) '
            '(rule OR regulation OR requirement OR update)'
        ),
    },
    {
        "source": "us_regulation",
        "source_name": "美国跨境法规",
        "kind": "跨境法规",
        "weight": 20,
        "query": (
            'site:cpsc.gov (ecommerce OR online marketplace OR consumer product) '
            '(rule OR regulation OR requirement OR safety)'
        ),
    },
)

POLICY_SIGNAL_WORDS = (
    "policy",
    "update",
    "requirement",
    "effective",
    "enforcement",
    "rule",
    "regulation",
    "compliance",
    "shipping",
    "fulfillment",
    "handling time",
    "listing",
    "title",
    "fee",
    "safety",
    "appeal",
    "settlement",
    "reserve",
    "tariff",
    "customs",
    "de minimis",
    "import",
    "labeling",
)

URGENT_WORDS = (
    "effective",
    "deadline",
    "before",
    "starting",
    "begin",
    "enforcement",
    "required",
    "requirement",
    "must",
)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def _clean_title(value: str) -> str:
    title = _strip_html(value)
    for suffix in (
        " - Amazon Seller Forums",
        " - Sell on Amazon",
        " - TikTok Shop Academy",
        " - TikTok Shop",
    ):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def _entry_datetime(entry):
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry,
        "updated_parsed",
        None,
    )
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _policy_relevance(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    matches = sum(1 for word in POLICY_SIGNAL_WORDS if word in text)
    urgent = sum(1 for word in URGENT_WORDS if word in text)
    return matches * 4 + min(urgent * 3, 12)


def _google_news_rss(query: str) -> str:
    encoded = quote_plus(query)
    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )


def _fetch_feed(query: str):
    response = requests.get(
        _google_news_rss(query),
        headers={"User-Agent": "AI-Intelligence-Radar/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


class PolicyCollector(BaseCollector):
    name = "policy"

    def collect(self, limit: int = 5):
        now = datetime.now(timezone.utc)
        oldest = now - timedelta(days=MAX_POLICY_AGE_DAYS)
        candidates = {}

        for source in POLICY_QUERIES:
            try:
                feed = _fetch_feed(source["query"])
            except Exception:
                logger.exception(
                    "政策源读取失败：%s",
                    source["source_name"],
                )
                continue

            for entry in getattr(feed, "entries", []) or []:
                created = _entry_datetime(entry)
                if created is None or created < oldest or created > now + timedelta(days=1):
                    continue

                title = _clean_title(getattr(entry, "title", ""))
                description = _strip_html(
                    getattr(entry, "summary", "")
                    or getattr(entry, "description", "")
                )
                if not title:
                    continue

                relevance = _policy_relevance(title, description)
                if relevance <= 0:
                    continue

                link = str(getattr(entry, "link", "") or "").strip()
                if not link:
                    continue

                age_days = max((now - created).total_seconds() / 86400, 0)
                recency = max(30 - age_days, 0)
                score = round(source["weight"] + relevance + recency, 2)

                key = re.sub(r"\W+", "", title.lower())[:140] or link
                existing = candidates.get(key)
                if existing and existing["metrics"]["policy_score"] >= score:
                    continue

                candidates[key] = {
                    "source": source["source"],
                    "title": title,
                    "url": link,
                    "description": description[:800],
                    "category": "policy",
                    "created_at": created.isoformat(),
                    "metrics": {
                        "policy_source": source["source_name"],
                        "policy_kind": source["kind"],
                        "policy_score": score,
                    },
                }

        results = list(candidates.values())
        results.sort(
            key=lambda item: (
                (item.get("metrics") or {}).get("policy_score", 0),
                item.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "政策采集完成：候选=%s 选中=%s",
            len(results),
            min(len(results), limit),
        )
        return results[:limit]


def fetch_policies(limit: int = 5):
    return PolicyCollector().collect_safe(limit)

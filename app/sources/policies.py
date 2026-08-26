from datetime import datetime, timedelta, timezone
import html
import re
from urllib.parse import quote_plus

import feedparser
import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


logger = get_logger("政策采集")

# lookback_days 决定搜索发现范围；report_days 决定“今天的日报”允许推多旧的内容。
# 搜索可以稍宽以识别同主题的新版本，但旧法规基线不能为了填满卡片冒充今日新规。
POLICY_QUERIES = (
    {
        "source": "amazon_policy",
        "source_name": "Amazon",
        "authority": "Amazon",
        "focus": "Amazon政策与审核",
        "kind": "平台政策",
        "weight": 44,
        "lookback_days": 60,
        "report_days": 21,
        "query": (
            'site:sellercentral.amazon.com/seller-forums/discussions News_Amazon '
            '(compliance OR "product safety" OR testing OR certification OR '
            'restricted OR requirement OR policy OR effective OR enforcement)'
        ),
    },
    {
        "source": "amazon_policy",
        "source_name": "Amazon",
        "authority": "Amazon",
        "focus": "Amazon政策与审核",
        "kind": "平台政策",
        "weight": 40,
        "lookback_days": 60,
        "report_days": 21,
        "query": (
            'site:sell.amazon.com/blog/announcements '
            '(compliance OR policy OR requirement OR "product safety" OR listing)'
        ),
    },
    {
        "source": "us_import_rule",
        "source_name": "美国海关 CBP",
        "authority": "CBP",
        "focus": "美国跨境新规",
        "kind": "进口与清关",
        "weight": 38,
        "lookback_days": 120,
        "report_days": 45,
        "query": (
            'site:cbp.gov (ecommerce OR e-commerce OR import OR de minimis OR customs) '
            '(rule OR regulation OR requirement OR tariff OR compliance OR update)'
        ),
    },
    {
        "source": "cpsc_compliance",
        "source_name": "美国消费品安全委员会 CPSC",
        "authority": "CPSC",
        "focus": "产品合规审核",
        "kind": "消费品安全",
        "weight": 42,
        "lookback_days": 120,
        "report_days": 45,
        "query": (
            'site:cpsc.gov (eFiling OR certificate OR certification OR testing OR '
            '"consumer product" OR importer) '
            '(requirement OR compliance OR rule OR effective OR safety)'
        ),
    },
    {
        "source": "fda_compliance",
        "source_name": "美国食品药品监督管理局 FDA",
        "authority": "FDA",
        "focus": "产品合规审核",
        "kind": "FDA准入",
        "weight": 36,
        "lookback_days": 120,
        "report_days": 45,
        "query": (
            'site:fda.gov (cosmetic OR cosmetics OR "medical device" OR food OR '
            '"dietary supplement") '
            '(registration OR listing OR import OR compliance OR requirement OR rule)'
        ),
    },
    {
        "source": "fcc_compliance",
        "source_name": "美国联邦通信委员会 FCC",
        "authority": "FCC",
        "focus": "产品合规审核",
        "kind": "无线与电子设备",
        "weight": 34,
        "lookback_days": 180,
        "report_days": 60,
        "query": (
            'site:fcc.gov ("equipment authorization" OR "RF device" OR radiofrequency) '
            '(import OR marketing OR certification OR compliance OR requirement)'
        ),
    },
)

POLICY_SIGNAL_WORDS = (
    "policy",
    "requirement",
    "effective",
    "enforcement",
    "rule",
    "regulation",
    "compliance",
    "testing",
    "inspection",
    "certification",
    "certificate",
    "laboratory",
    "lab",
    "registration",
    "product listing",
    "authorization",
    "efiling",
    "efile",
    "restricted",
    "prohibited",
    "recall",
    "safety",
    "import",
    "customs",
    "tariff",
    "de minimis",
    "labeling",
    "documentation",
    "appeal",
)

URGENT_WORDS = (
    "effective",
    "deadline",
    "starting",
    "enforcement",
    "required",
    "requirement",
    "must",
    "prohibited",
    "suspend",
    "remove",
    "cannot",
    "no longer",
)

# 主题相似度判定时忽略这些泛化词，避免“Amazon policy update”本身造成虚假相似。
TOPIC_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with", "us", "u", "s", "new", "news", "update",
    "updates", "policy", "policies", "rule", "rules", "requirement", "requirements",
    "compliance", "amazon", "seller", "sellers", "selling", "product", "products",
}


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def _clean_title(value: str) -> str:
    title = _strip_html(value)
    for suffix in (
        " - Amazon Seller Forums",
        " - Sell on Amazon",
        " | CPSC.gov",
        " | FDA",
        " | Federal Communications Commission",
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


def _signal_counts(title: str, description: str):
    title_text = title.lower()
    body_text = description.lower()
    title_hits = sum(1 for word in POLICY_SIGNAL_WORDS if word in title_text)
    body_hits = sum(1 for word in POLICY_SIGNAL_WORDS if word in body_text)
    urgent_hits = sum(
        1
        for word in URGENT_WORDS
        if word in title_text or word in body_text
    )
    return title_hits, body_hits, urgent_hits


def _policy_relevance(title: str, description: str) -> int:
    title_hits, body_hits, urgent_hits = _signal_counts(title, description)
    if title_hits == 0 and body_hits < 2:
        return 0
    return title_hits * 7 + body_hits * 3 + min(urgent_hits * 4, 16)


def _topic_tokens(title: str):
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    return {
        word
        for word in words
        if len(word) >= 3 and word not in TOPIC_STOPWORDS
    }


def _same_policy_topic(left: dict, right: dict) -> bool:
    """同一监管机构、同一板块内才允许按标题相似度判为同一政策主题。"""
    left_metrics = left.get("metrics") or {}
    right_metrics = right.get("metrics") or {}
    if left_metrics.get("policy_focus") != right_metrics.get("policy_focus"):
        return False

    left_authority = str(left_metrics.get("policy_authority") or "").strip().lower()
    right_authority = str(right_metrics.get("policy_authority") or "").strip().lower()
    if left_authority and right_authority and left_authority != right_authority:
        return False

    left_title = re.sub(r"\W+", " ", str(left.get("title") or "").lower()).strip()
    right_title = re.sub(r"\W+", " ", str(right.get("title") or "").lower()).strip()
    if left_title and right_title and (left_title in right_title or right_title in left_title):
        return True

    left_tokens = _topic_tokens(left_title)
    right_tokens = _topic_tokens(right_title)
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    union = len(left_tokens | right_tokens)
    jaccard = overlap / max(union, 1)
    return containment >= 0.72 or (overlap >= 3 and jaccard >= 0.48)


def _dedupe_policy_topics(items):
    """同一监管机构的同一政策主题只保留发布时间最新的一条。"""
    ordered = sorted(
        items,
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )
    kept = []
    duplicate_count = 0
    for item in ordered:
        if any(_same_policy_topic(item, existing) for existing in kept):
            duplicate_count += 1
            continue
        kept.append(item)
    return kept, duplicate_count


def _candidate_key(title: str, authority: str, link: str) -> str:
    """候选字典在主题去重前也必须隔离监管机构，防止同名 CPSC/FDA/FCC 互相覆盖。"""
    normalized = re.sub(r"\W+", "", str(title or "").lower())[:160]
    authority_key = re.sub(r"\W+", "", str(authority or "").lower()) or "unknown"
    return f"{authority_key}:{normalized or link}"


def _recency_first_score(created: datetime, source_weight: int, relevance: int) -> float:
    """生成时间优先的内部排序键；每晚一小时都比旧内容优先，质量只用于同小时附近破平局。"""
    hour_rank = created.timestamp() / 3600
    quality_tiebreak = min(max(source_weight + relevance, 0), 999) / 1000
    return round(hour_rank + quality_tiebreak, 3)


def _within_report_window(created: datetime, now: datetime, report_days: int) -> bool:
    """日报只推近期变化；旧法规可用于搜索背景，但不能作为“今日新规”进入日报。"""
    try:
        days = max(int(report_days), 1)
    except (TypeError, ValueError):
        days = 30
    return now - timedelta(days=days) <= created <= now + timedelta(days=1)


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

    def collect(self, limit: int = 8):
        now = datetime.now(timezone.utc)
        candidates = {}
        stale_rejected = 0

        for source in POLICY_QUERIES:
            oldest = now - timedelta(days=source["lookback_days"])

            try:
                feed = _fetch_feed(source["query"])
            except Exception:
                logger.exception("政策源读取失败：%s", source["source_name"])
                continue

            for entry in getattr(feed, "entries", []) or []:
                created = _entry_datetime(entry)
                if created is None or created < oldest or created > now + timedelta(days=1):
                    continue

                # 搜索范围可以较宽，但日报只接受本来源规定的新鲜度窗口。
                if not _within_report_window(created, now, source.get("report_days", 30)):
                    stale_rejected += 1
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

                age_hours = max((now - created).total_seconds() / 3600, 0)
                score = _recency_first_score(created, source["weight"], relevance)

                key = _candidate_key(title, source["authority"], link)
                existing = candidates.get(key)
                if existing:
                    existing_time = existing.get("created_at") or ""
                    if existing_time >= created.isoformat():
                        continue

                candidates[key] = {
                    "source": source["source"],
                    "title": title,
                    "url": link,
                    "description": description,
                    "category": "policy",
                    "created_at": created.isoformat(),
                    "metrics": {
                        "policy_source": source["source_name"],
                        "policy_authority": source["authority"],
                        "policy_focus": source["focus"],
                        "policy_kind": source["kind"],
                        "policy_score": score,
                        "policy_relevance_score": relevance,
                        "age_hours": round(age_hours, 1),
                        "lookback_days": source["lookback_days"],
                        "report_days": source.get("report_days", 30),
                    },
                }

        results, duplicate_count = _dedupe_policy_topics(list(candidates.values()))
        results.sort(
            key=lambda item: (
                item.get("created_at") or "",
                (item.get("metrics") or {}).get("policy_relevance_score", 0),
            ),
            reverse=True,
        )

        logger.info(
            "政策采集完成：原始候选=%s 过期淘汰=%s 同主题去重=%s 合格=%s 选中=%s",
            len(candidates),
            stale_rejected,
            duplicate_count,
            len(results),
            min(len(results), limit),
        )
        return results[:limit]


def fetch_policies(limit: int = 8):
    return PolicyCollector().collect_safe(limit)

from datetime import datetime, timedelta, timezone
import html
import re
from urllib.parse import quote_plus

import feedparser
import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


logger = get_logger("政策采集")

# 不同监管主题变化频率不同。Amazon 关注更近期，CPSC/FDA/FCC 等产品准入规则
# 使用更长窗口，避免错过已经开始执行但仍直接影响新品进入美国市场的重要要求。
POLICY_QUERIES = (
    {
        "source": "amazon_policy",
        "source_name": "Amazon",
        "authority": "Amazon",
        "focus": "Amazon政策与审核",
        "kind": "平台政策",
        "weight": 44,
        "lookback_days": 60,
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

    # 标题明确出现规则/合规信号时直接保留；否则正文至少需要两个不同信号，
    # 避免普通营销文章因为偶然出现 policy/update 等单词进入日报。
    if title_hits == 0 and body_hits < 2:
        return 0

    return title_hits * 7 + body_hits * 3 + min(urgent_hits * 4, 16)


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

        for source in POLICY_QUERIES:
            oldest = now - timedelta(days=source["lookback_days"])

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
                recency_ratio = max(
                    1 - age_days / max(source["lookback_days"], 1),
                    0,
                )
                recency = recency_ratio * 24
                score = round(source["weight"] + relevance + recency, 2)

                key = re.sub(r"\W+", "", title.lower())[:160] or link
                existing = candidates.get(key)
                if existing and existing["metrics"]["policy_score"] >= score:
                    continue

                candidates[key] = {
                    "source": source["source"],
                    "title": title,
                    "url": link,
                    "description": description[:1200],
                    "category": "policy",
                    "created_at": created.isoformat(),
                    "metrics": {
                        "policy_source": source["source_name"],
                        "policy_authority": source["authority"],
                        "policy_focus": source["focus"],
                        "policy_kind": source["kind"],
                        "policy_score": score,
                        "lookback_days": source["lookback_days"],
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


def fetch_policies(limit: int = 8):
    return PolicyCollector().collect_safe(limit)

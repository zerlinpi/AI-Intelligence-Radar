from datetime import datetime, timezone
from typing import Dict, List
import re

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


logger = get_logger("Hacker News采集")

AI_KEYWORDS = (
    "llm",
    "gpt",
    "agent",
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "machine learning",
    "generative ai",
    "chatbot",
    "inference",
    "rag",
    "embedding",
    "copilot",
    "transformer",
)


def _is_ai_story(title: str) -> bool:
    normalized = (title or "").lower()

    if re.search(r"\bai\b", normalized):
        return True

    return any(keyword in normalized for keyword in AI_KEYWORDS)


class HackerNewsCollector(BaseCollector):
    name = "hackernews"

    def collect(self, limit: int = 10) -> List[Dict]:
        # Show HN 更适合发现刚发布的项目，而不是历史热门内容。
        api = "https://hacker-news.firebaseio.com/v0/showstories.json"

        response = requests.get(api, timeout=10)
        response.raise_for_status()

        ids = response.json()
        if not isinstance(ids, list):
            return []

        results = []
        now = datetime.now(timezone.utc)
        candidate_limit = max(limit * 3, 20)

        for item_id in ids[:80]:
            if len(results) >= candidate_limit:
                break

            try:
                response = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                    timeout=10,
                )
                response.raise_for_status()

                item = response.json()
                if not isinstance(item, dict):
                    continue

                title = item.get("title") or ""
                if not _is_ai_story(title):
                    continue

                timestamp = item.get("time")
                if not timestamp:
                    continue

                created = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                created_at = created.isoformat()
                age_hours = max((now - created).total_seconds() / 3600, 1)

                # 只保留近期发布，避免旧讨论混入早期项目雷达。
                if age_hours > 24 * 14:
                    continue

                score = item.get("score") or 0
                comments = item.get("descendants") or 0
                momentum = (score + comments * 2) / max(age_hours / 24, 0.25)
                url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"

                results.append(
                    {
                        "source": self.name,
                        "title": title,
                        "url": url,
                        "description": title,
                        "created_at": created_at,
                        "upvotes": score,
                        "comments": comments,
                        "metrics": {
                            "upvotes": score,
                            "comments": comments,
                            "momentum": round(momentum, 2),
                        },
                    }
                )
            except Exception:
                logger.exception("Hacker News 项目获取失败：编号=%s", item_id)
                continue

        results.sort(
            key=lambda x: (x.get("metrics") or {}).get("momentum", 0),
            reverse=True,
        )
        return results[:limit]


def fetch_hackernews(limit=10):
    return HackerNewsCollector().collect_safe(limit)

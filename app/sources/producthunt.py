from datetime import datetime, timedelta, timezone
from typing import Dict, List
import os

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


API = "https://api.producthunt.com/v2/api/graphql"
logger = get_logger("collector.producthunt")

AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "llm",
    "agent",
    "machine learning",
    "generative",
    "copilot",
    "automation",
)


def _is_ai_product(node: Dict) -> bool:
    topic_names = []
    topics = node.get("topics") or {}
    edges = topics.get("edges") if isinstance(topics, dict) else []

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            topic = edge.get("node") or {}
            if isinstance(topic, dict):
                topic_names.extend(
                    [
                        str(topic.get("name") or ""),
                        str(topic.get("slug") or ""),
                    ]
                )

    haystack = " ".join(
        [
            str(node.get("name") or ""),
            str(node.get("tagline") or ""),
            str(node.get("description") or ""),
            *topic_names,
        ]
    ).lower()

    return any(keyword in haystack for keyword in AI_KEYWORDS)


class ProductHuntCollector(BaseCollector):
    name = "producthunt"

    def collect(self, limit: int = 10) -> List[Dict]:
        token = os.getenv("PRODUCT_HUNT_TOKEN", "").strip()
        if not token:
            logger.warning("PRODUCT_HUNT_TOKEN is not configured")
            return []

        posted_after = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        fetch_limit = min(max(limit * 5, 30), 50)
        query = """
        query RecentAIProducts($first: Int!, $postedAfter: DateTime!) {
          posts(first: $first, order: VOTES, postedAfter: $postedAfter) {
            edges {
              node {
                id
                name
                tagline
                description
                url
                website
                votesCount
                commentsCount
                createdAt
                topics(first: 5) {
                  edges {
                    node {
                      name
                      slug
                    }
                  }
                }
              }
            }
          }
        }
        """

        response = requests.post(
            API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "variables": {
                    "first": fetch_limit,
                    "postedAfter": posted_after,
                },
            },
            timeout=20,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            logger.warning("product hunt returned invalid payload")
            return []

        errors = payload.get("errors")
        if errors:
            logger.error("product hunt graphql errors=%s", errors)
            return []

        data = payload.get("data") or {}
        posts = data.get("posts") if isinstance(data, dict) else {}
        edges = posts.get("edges") if isinstance(posts, dict) else []
        if not isinstance(edges, list):
            return []

        results = []
        now = datetime.now(timezone.utc)

        for edge in edges:
            if not isinstance(edge, dict):
                continue

            node = edge.get("node") or {}
            if not isinstance(node, dict) or not _is_ai_product(node):
                continue

            created_at = node.get("createdAt")
            try:
                created = datetime.fromisoformat(
                    str(created_at).replace("Z", "+00:00")
                )
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max((now - created).total_seconds() / 3600, 1)
            except Exception:
                age_hours = 24 * 7

            votes = node.get("votesCount") or 0
            comments = node.get("commentsCount") or 0
            momentum = (votes + comments * 3) / max(age_hours / 24, 0.25)

            results.append(
                {
                    "source": self.name,
                    "title": node.get("name") or "",
                    "url": node.get("website") or node.get("url") or "",
                    "description": node.get("tagline") or node.get("description") or "",
                    "created_at": created_at,
                    "upvotes": votes,
                    "comments": comments,
                    "metrics": {
                        "upvotes": votes,
                        "comments": comments,
                        "momentum": round(momentum, 2),
                        "producthunt_url": node.get("url") or "",
                    },
                }
            )

        results.sort(
            key=lambda x: (x.get("metrics") or {}).get("momentum", 0),
            reverse=True,
        )
        return results[:limit]


def fetch_producthunt(limit: int = 10):
    return ProductHuntCollector().collect_safe(limit)

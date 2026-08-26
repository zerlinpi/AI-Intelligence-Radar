from datetime import datetime, timezone
from typing import Dict, List
import os
import re

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger
from app.relevance import attach_eligibility_metrics, report_eligibility


API = "https://api.producthunt.com/v2/api/graphql"
logger = get_logger("Product Hunt采集")

AI_KEYWORDS = (
    "artificial intelligence",
    "llm",
    "gpt",
    "agent",
    "agents",
    "chatbot",
    "machine learning",
    "generative",
    "copilot",
    "automation",
    "vision",
    "voice ai",
    "speech ai",
)

MAX_AGE_DAYS = 7


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

    if re.search(r"\bai\b", haystack):
        return True

    return any(keyword in haystack for keyword in AI_KEYWORDS)


def _parse_created_at(value):
    if not value:
        return None

    try:
        created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created
    except Exception:
        return None


def _product_description(node: Dict) -> str:
    """同时保留 tagline 与 description，为后续 AI 分析提供足够产品语义。"""
    tagline = " ".join(str(node.get("tagline") or "").split()).strip()
    description = " ".join(str(node.get("description") or "").split()).strip()

    if tagline and description:
        if description.lower().startswith(tagline.lower()):
            return description
        return f"{tagline}。{description}"
    return description or tagline


class ProductHuntCollector(BaseCollector):
    name = "producthunt"

    def collect(self, limit: int = 10) -> List[Dict]:
        token = os.getenv("PRODUCT_HUNT_TOKEN", "").strip()
        if not token:
            logger.warning("未配置 PRODUCT_HUNT_TOKEN，已跳过 Product Hunt")
            return []

        fetch_limit = min(max(limit * 6, 40), 50)

        query = """
        query RecentProducts($first: Int!) {
          posts(first: $first) {
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
                "variables": {"first": fetch_limit},
            },
            timeout=20,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            logger.warning("Product Hunt 返回数据格式无效")
            return []

        errors = payload.get("errors")
        if errors:
            logger.error("Product Hunt 图查询返回错误=%s", errors)
            return []

        data = payload.get("data") or {}
        posts = data.get("posts") if isinstance(data, dict) else {}
        edges = posts.get("edges") if isinstance(posts, dict) else []
        if not isinstance(edges, list):
            logger.warning("Product Hunt 返回内容中缺少产品列表")
            return []

        results = []
        rejected = 0
        now = datetime.now(timezone.utc)

        for edge in edges:
            if not isinstance(edge, dict):
                continue

            node = edge.get("node") or {}
            if not isinstance(node, dict) or not _is_ai_product(node):
                continue

            created_at = node.get("createdAt")
            created = _parse_created_at(created_at)
            if created is None:
                continue

            age_hours = max((now - created).total_seconds() / 3600, 0)
            if age_hours > MAX_AGE_DAYS * 24:
                continue

            votes = node.get("votesCount") or 0
            comments = node.get("commentsCount") or 0
            age_days = max(age_hours / 24, 0.25)
            momentum = (votes + comments * 3) / age_days

            record = {
                "source": self.name,
                "title": node.get("name") or "",
                "url": node.get("website") or node.get("url") or "",
                "description": _product_description(node),
                "created_at": created_at,
                "upvotes": votes,
                "comments": comments,
                "metrics": {
                    "upvotes": votes,
                    "comments": comments,
                    "momentum": round(momentum, 2),
                    "producthunt_url": node.get("url") or "",
                    "website": node.get("website") or "",
                },
            }

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            if not eligibility["eligible"]:
                rejected += 1
                continue

            results.append(record)

        results.sort(
            key=lambda x: (
                float((x.get("metrics") or {}).get("opportunity_score", 0) or 0),
                float((x.get("metrics") or {}).get("momentum", 0) or 0),
                x.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "Product Hunt 获取=%s 资格淘汰=%s 合格=%s 最终返回=%s",
            len(edges),
            rejected,
            len(results),
            min(len(results), limit),
        )

        return results[:limit]


def fetch_producthunt(limit: int = 10):
    return ProductHuntCollector().collect_safe(limit)

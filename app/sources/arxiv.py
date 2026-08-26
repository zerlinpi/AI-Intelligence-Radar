from typing import Dict, List
from xml.etree import ElementTree

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger


API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

logger = get_logger("arXiv采集")


class ArxivCollector(BaseCollector):
    name = "arxiv"

    def collect(self, limit: int = 15) -> List[Dict]:
        params = {
            # 在通用 AI/ML/NLP 基础上加入机器人与计算机视觉，提升发现硬件、
            # 视觉传感、边缘设备和实体产品技术机会的概率。
            "search_query": (
                "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR "
                "cat:cs.RO OR cat:cs.CV"
            ),
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        response = requests.get(API, params=params, timeout=20)
        response.raise_for_status()

        text = response.text or ""
        if not text.strip():
            return []

        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            logger.exception("arXiv 返回的论文数据格式无效")
            return []

        results = []
        for entry in root.findall("atom:entry", ATOM_NS):
            title = " ".join(
                (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").split()
            )
            summary = " ".join(
                (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").split()
            )
            created_at = entry.findtext(
                "atom:published",
                default="",
                namespaces=ATOM_NS,
            )
            url = entry.findtext("atom:id", default="", namespaces=ATOM_NS) or ""

            categories = []
            for category in entry.findall("atom:category", ATOM_NS):
                term = category.attrib.get("term")
                if term:
                    categories.append(term)

            if not title or not url:
                continue

            description = summary
            if categories:
                description = f"{summary} | categories: {' '.join(categories)}"

            results.append(
                {
                    "source": self.name,
                    "title": title,
                    "url": url,
                    "description": description,
                    "created_at": created_at or None,
                    "metrics": {
                        "topics": categories,
                    },
                }
            )

        return results[:limit]


def fetch_ai_papers(limit=15):
    return ArxivCollector().collect_safe(limit)

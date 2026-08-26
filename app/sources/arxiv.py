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

    def collect(self, limit: int = 10) -> List[Dict]:
        params = {
            "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
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

            if not title or not url:
                continue

            results.append(
                {
                    "source": self.name,
                    "title": title,
                    "url": url,
                    # 保留 arXiv 原始摘要全文。模型输入层可独立做上下文预算控制，
                    # 但源数据本身不应提前裁掉，确保降级展示和后续再分析都有完整材料。
                    "description": summary,
                    "created_at": created_at or None,
                    "metrics": {},
                }
            )

        return results[:limit]


def fetch_ai_papers(limit=10):
    return ArxivCollector().collect_safe(limit)

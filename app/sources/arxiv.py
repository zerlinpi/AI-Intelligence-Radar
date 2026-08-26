from typing import Dict, List
from xml.etree import ElementTree

import requests

from app.sources.base import BaseCollector
from app.core.logger import get_logger
from app.relevance import attach_eligibility_metrics, report_eligibility


API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

logger = get_logger("arXiv采集")


class ArxivCollector(BaseCollector):
    name = "arxiv"

    def collect(self, limit: int = 15) -> List[Dict]:
        # 严格门槛会淘汰大量纯理论论文，因此先扩大近期候选池，再按“对跨境/硬件/实体商品是否有用”筛选。
        fetch_limit = min(max(limit * 8, 80), 200)
        params = {
            "search_query": (
                "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR "
                "cat:cs.RO OR cat:cs.CV"
            ),
            "start": 0,
            "max_results": fetch_limit,
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
        rejected = 0
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

            record = {
                "source": self.name,
                "title": title,
                "url": url,
                "description": description,
                "created_at": created_at or None,
                "metrics": {
                    "topics": categories,
                },
            }

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            if not eligibility["eligible"]:
                rejected += 1
                continue

            results.append(record)

        # 论文只在通过资格门槛后比较“帮助度 + 时间”。纯技术前沿但无法落地的不进入这里。
        results.sort(
            key=lambda item: (
                float((item.get("metrics") or {}).get("opportunity_score", 0) or 0),
                item.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "arXiv 近期候选=%s 资格淘汰=%s 合格=%s 最终返回=%s",
            len(root.findall("atom:entry", ATOM_NS)),
            rejected,
            len(results),
            min(len(results), limit),
        )
        return results[:limit]


def fetch_ai_papers(limit=15):
    return ArxivCollector().collect_safe(limit)

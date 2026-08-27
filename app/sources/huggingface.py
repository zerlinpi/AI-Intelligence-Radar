from datetime import datetime, timezone
import re
from typing import Dict, List

import requests

from app.commercial_readiness import attach_commercial_metrics, commercial_readiness
from app.core.logger import get_logger
from app.sources.base import BaseCollector
from app.relevance import attach_eligibility_metrics, report_eligibility


API = "https://huggingface.co/api/models"
MODEL_CARD_ENRICH_LIMIT = 20
MODEL_CARD_TEXT_LIMIT = 4500

logger = get_logger("Hugging Face采集")


def _clean_model_card(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""

    # YAML front matter、图片、HTML、大段代码对用途判断帮助有限，优先保留模型说明正文。
    text = re.sub(r"\A---\s*.*?\s*---", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[>#]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`*_~]+", " ", text)
    text = " ".join(text.split())
    return text[:MODEL_CARD_TEXT_LIMIT]


def _fetch_model_card(model_id: str) -> str:
    if not model_id:
        return ""

    try:
        response = requests.get(
            f"https://huggingface.co/{model_id}/raw/main/README.md",
            timeout=12,
            headers={"User-Agent": "AI-Intelligence-Radar/1.0"},
        )
        if response.status_code in {401, 403, 404}:
            return ""
        response.raise_for_status()
        return _clean_model_card(response.text)
    except Exception:
        return ""


def _record_from_item(item: dict, now: datetime):
    model_id = item.get("modelId") or ""
    created_at = item.get("createdAt")
    if not model_id or not created_at:
        return None

    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = max((now - created).total_seconds() / 3600, 1)
    except Exception:
        return None

    if age_hours > 24 * 7:
        return None

    downloads = item.get("downloads") or 0
    likes = item.get("likes") or 0
    momentum = (downloads + likes * 200) / max(age_hours / 24, 0.25)

    pipeline_tag = item.get("pipeline_tag") or ""
    library_name = item.get("library_name") or ""
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    description_parts = []
    if pipeline_tag:
        description_parts.append(f"task: {pipeline_tag}")
    if library_name:
        description_parts.append(f"library: {library_name}")
    if tags:
        description_parts.append("tags: " + " ".join(str(tag) for tag in tags))
    if not description_parts:
        description_parts.append("新发布 AI 模型")

    record = {
        "source": "huggingface",
        "title": model_id,
        "url": f"https://huggingface.co/{model_id}",
        "description": " | ".join(description_parts),
        "created_at": created_at,
        "downloads": downloads,
        "metrics": {
            "downloads": downloads,
            "likes": likes,
            "momentum": round(momentum, 2),
            "pipeline_tag": pipeline_tag,
            "library_name": library_name,
            "tags": tags,
            "model_card_evidence": False,
            "model_card_chars": 0,
        },
    }
    attach_commercial_metrics(record)
    return record


def _preliminary_score(record: dict) -> tuple:
    eligibility = report_eligibility(record)
    profile = eligibility.get("profile") or {}
    opportunity_score = float(profile.get("opportunity_score", 0) or 0)
    commercial_score = float((record.get("metrics") or {}).get("commercial_readiness_score", 0) or 0)
    momentum = float((record.get("metrics") or {}).get("momentum", 0) or 0)
    return opportunity_score, commercial_score, momentum


class HuggingFaceCollector(BaseCollector):
    name = "huggingface"

    def collect(self, limit: int = 15) -> List[Dict]:
        fetch_limit = min(max(limit * 8, 80), 100)
        params = {
            "sort": "createdAt",
            "direction": -1,
            "limit": fetch_limit,
        }

        response = requests.get(API, params=params, timeout=20)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, list):
            return []

        now = datetime.now(timezone.utc)
        preliminary = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = _record_from_item(item, now)
            if record is not None:
                preliminary.append(record)

        # Model Card 请求优先给“机会高 + 许可证商业可用性清晰”的模型。
        preliminary.sort(key=_preliminary_score, reverse=True)
        enrich_count = min(max(limit * 2, 12), MODEL_CARD_ENRICH_LIMIT, len(preliminary))

        for record in preliminary[:enrich_count]:
            model_card = _fetch_model_card(record["title"])
            if not model_card:
                continue
            record["description"] = " | ".join(
                part
                for part in (
                    record.get("description") or "",
                    f"MODEL_CARD: {model_card}",
                )
                if part
            )
            metrics = record.get("metrics") or {}
            metrics["model_card_evidence"] = True
            metrics["model_card_chars"] = len(model_card)
            record["metrics"] = metrics

        results = []
        rejected = 0
        license_rejected = 0
        enriched = 0

        for record in preliminary:
            # Model Card 可能补充明确的 Non-Commercial / Research-Only 限制，
            # 必须在增强后重新计算许可证商业可用性。
            commercial = commercial_readiness(record)
            if not commercial["commercial_candidate"]:
                attach_commercial_metrics(record, commercial)
                license_rejected += 1
                continue

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            # 资格证据写完之后再附加许可证据，确保 analyzer 的“据=”能收到许可证风险。
            attach_commercial_metrics(record, commercial)
            if not eligibility["eligible"]:
                rejected += 1
                continue
            if (record.get("metrics") or {}).get("model_card_evidence"):
                enriched += 1
            results.append(record)

        # 模型首先看真实业务/实体产品价值，其次看许可证商业可用性，最后才看下载/点赞热度。
        results.sort(
            key=lambda x: (
                float((x.get("metrics") or {}).get("opportunity_score", 0) or 0),
                float((x.get("metrics") or {}).get("commercial_readiness_score", 0) or 0),
                float((x.get("metrics") or {}).get("momentum", 0) or 0),
                x.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "Hugging Face 近期候选=%s Model Card增强=%s 许可淘汰=%s 资格淘汰=%s 合格=%s 最终返回=%s",
            len(preliminary),
            enriched,
            license_rejected,
            rejected,
            len(results),
            min(len(results), limit),
        )
        return results[:limit]


def fetch_models(limit=15):
    return HuggingFaceCollector().collect_safe(limit)

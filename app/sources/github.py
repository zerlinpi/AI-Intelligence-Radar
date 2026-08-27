from datetime import datetime, timedelta, timezone
import re

import requests

from app.commercial_readiness import attach_commercial_metrics, commercial_readiness
from app.config import GITHUB_TOKEN
from app.deployment_readiness import attach_deployment_metrics, deployment_readiness
from app.sources.base import BaseCollector
from app.core.logger import get_logger
from app.relevance import attach_eligibility_metrics, report_eligibility


SEARCH_API = "https://api.github.com/search/repositories"
README_ENRICH_LIMIT = 24
README_TEXT_LIMIT = 4500

logger = get_logger("GitHub采集")

SEARCH_TERMS = (
    "topic:ai",
    "llm in:name,description",
    '"ai agent" in:name,description',
    '"edge ai" in:name,description',
    '"embedded ai" in:name,description',
    '"robotics ai" in:name,description',
    '"computer vision" in:name,description',
    '"on-device ai" in:name,description',
    '"amazon seller" in:name,description',
    '"shopify" ai in:name,description',
)


def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _clean_readme(value: str) -> str:
    """把 README 转成适合相关性判断和 DeepSeek 阅读的纯文本证据。"""
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[>#]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`*_~]+", " ", text)
    text = " ".join(text.split())
    return text[:README_TEXT_LIMIT]


def _fetch_readme(full_name: str, headers: dict) -> str:
    if not full_name:
        return ""
    try:
        response = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers={**headers, "Accept": "application/vnd.github.raw+json"},
            timeout=12,
        )
        if response.status_code == 404:
            return ""
        response.raise_for_status()
        return _clean_readme(response.text)
    except Exception:
        return ""


def _license_spdx(item: dict) -> str:
    license_data = item.get("license") or {}
    if not isinstance(license_data, dict):
        return ""
    value = str(license_data.get("spdx_id") or "").strip()
    return "" if value.upper() in {"NOASSERTION", "OTHER"} else value


def _build_record(item: dict, now: datetime):
    created_at = item.get("created_at")
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = max((now - created).total_seconds() / 3600, 1)
    except Exception:
        return None

    stars = item.get("stargazers_count", 0) or 0
    forks = item.get("forks_count", 0) or 0
    open_issues = item.get("open_issues_count", 0) or 0
    age_days = max(age_hours / 24, 0.25)
    momentum = (stars + forks * 3) / age_days
    topics = item.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    language = str(item.get("language") or "").strip()
    license_spdx = _license_spdx(item)
    homepage = str(item.get("homepage") or "").strip()
    repo_size_kb = item.get("size", 0) or 0

    description_parts = []
    if item.get("description"):
        description_parts.append(str(item.get("description")))
    if topics:
        description_parts.append("topics: " + " ".join(str(topic) for topic in topics))
    if language:
        description_parts.append(f"language: {language}")
    if license_spdx:
        description_parts.append(f"license: {license_spdx}")

    record = {
        "source": "github",
        "title": item.get("full_name") or item.get("name") or "",
        "url": item.get("html_url") or "",
        "description": " | ".join(part for part in description_parts if part),
        "created_at": created_at,
        "stars": stars,
        "forks": forks,
        "metrics": {
            "github_id": item.get("id"),
            "stars": stars,
            "forks": forks,
            "open_issues": open_issues,
            "repo_size_kb": repo_size_kb,
            "momentum": round(momentum, 2),
            "topics": topics,
            "language": language,
            "license_spdx": license_spdx,
            "homepage": homepage,
            "archived": bool(item.get("archived")),
            "disabled": bool(item.get("disabled")),
            "updated_at": item.get("updated_at") or "",
            "pushed_at": item.get("pushed_at") or "",
            "default_branch": item.get("default_branch") or "",
            "readme_evidence": False,
            "readme_chars": 0,
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


class GithubCollector(BaseCollector):
    name = "github"

    def collect(self, limit: int = 15):
        headers = _headers()
        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=7)).date().isoformat()
        fetch_limit = min(max(limit * 4, 40), 60)
        candidates = {}

        for search_term in SEARCH_TERMS:
            params = {
                "q": f"{search_term} created:>={since} stars:>=5 fork:false archived:false",
                "sort": "stars",
                "order": "desc",
                "per_page": fetch_limit,
            }
            try:
                response = requests.get(SEARCH_API, headers=headers, params=params, timeout=20)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    logger.warning("GitHub 接口返回数据格式无效：查询=%s", search_term)
                    continue
                items = payload.get("items", [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("id") or item.get("html_url")
                    if key:
                        candidates[key] = item
            except Exception:
                logger.exception("GitHub 搜索失败：查询=%s", search_term)
                continue

        preliminary = []
        for raw in candidates.values():
            record = _build_record(raw, now)
            if record is not None:
                preliminary.append((record, raw))

        preliminary.sort(key=lambda pair: _preliminary_score(pair[0]), reverse=True)
        enrich_count = min(max(limit * 2, 12), README_ENRICH_LIMIT, len(preliminary))

        for record, raw in preliminary[:enrich_count]:
            full_name = str(raw.get("full_name") or "").strip()
            readme = _fetch_readme(full_name, headers)
            if not readme:
                continue
            record["description"] = " | ".join(
                part for part in (record.get("description") or "", f"README: {readme}") if part
            )
            metrics = record.get("metrics") or {}
            metrics["readme_evidence"] = True
            metrics["readme_chars"] = len(readme)
            record["metrics"] = metrics

        result = []
        rejected = 0
        license_rejected = 0
        deployment_rejected = 0
        enriched = 0

        for record, _raw in preliminary:
            commercial = commercial_readiness(record)
            if not commercial["commercial_candidate"]:
                attach_commercial_metrics(record, commercial)
                license_rejected += 1
                continue

            eligibility = report_eligibility(record)
            attach_eligibility_metrics(record, eligibility)
            # 资格证据写完之后再附加许可证据，确保 analyzer 的“据=”包含商业复用风险。
            attach_commercial_metrics(record, commercial)
            if not eligibility["eligible"]:
                rejected += 1
                continue

            readiness = deployment_readiness(record)
            attach_deployment_metrics(record, readiness)
            if not readiness["eligible"]:
                deployment_rejected += 1
                continue

            if (record.get("metrics") or {}).get("readme_evidence"):
                enriched += 1
            result.append(record)

        result.sort(
            key=lambda x: (
                float((x.get("metrics") or {}).get("opportunity_score", 0) or 0),
                float((x.get("metrics") or {}).get("commercial_readiness_score", 0) or 0),
                float((x.get("metrics") or {}).get("deployment_readiness_score", 0) or 0),
                float((x.get("metrics") or {}).get("momentum", 0) or 0),
                x.get("created_at") or "",
            ),
            reverse=True,
        )

        logger.info(
            "GitHub 近期候选=%s README增强=%s 许可淘汰=%s 资格淘汰=%s 部署淘汰=%s 合格=%s 最终返回=%s",
            len(candidates),
            enriched,
            license_rejected,
            rejected,
            deployment_rejected,
            len(result),
            min(len(result), limit),
        )
        return result[:limit]


def fetch_ai_repositories(limit: int = 15):
    return GithubCollector().collect_safe(limit)

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
ENGINEERING_TREE_ENRICH_LIMIT = 12

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

_CODE_EXTENSIONS = {
    ".py", ".pyx", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".kt", ".kts", ".swift", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh",
    ".hpp", ".ino", ".lua", ".rb", ".php", ".cs", ".dart", ".scala", ".sh",
}

_PACKAGE_CONFIG_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "poetry.lock",
    "pipfile", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "bun.lockb", "cargo.toml", "cargo.lock", "go.mod", "go.sum", "pom.xml",
    "build.gradle", "build.gradle.kts", "cmakelists.txt", "platformio.ini",
    "idf_component.yml", "idf_component.yaml",
}

_DEPLOYMENT_FILE_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "procfile", "fly.toml", "render.yaml", "vercel.json",
}


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


def _fetch_engineering_tree(full_name: str, default_branch: str, headers: dict):
    """读取仓库文件树，用实际文件组成验证代码、包配置、测试与 CI 资产。

    读取失败返回 None，不让额外的工程增强请求拖垮主采集；成功但仓库没有文件则返回空列表，
    由部署成熟度 Gate 把“有 README/体量元数据但没有真实代码”的异常候选挡掉。
    """
    if not full_name or not default_branch:
        return None
    try:
        response = requests.get(
            f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}",
            headers=headers,
            params={"recursive": "1"},
            timeout=15,
        )
        if response.status_code in {403, 404}:
            return None
        response.raise_for_status()
        payload = response.json()
        tree = payload.get("tree") if isinstance(payload, dict) else None
        if not isinstance(tree, list):
            return None
        return [
            str(row.get("path") or "").strip()
            for row in tree
            if isinstance(row, dict)
            and row.get("type") == "blob"
            and str(row.get("path") or "").strip()
        ]
    except Exception:
        return None


def _engineering_tree_profile(paths) -> dict:
    files = [str(path or "").strip() for path in (paths or []) if str(path or "").strip()]
    lower_files = [path.lower() for path in files]

    code_files = []
    package_configs = []
    deployment_files = []
    test_files = []
    ci_files = []

    for path, lower_path in zip(files, lower_files):
        basename = lower_path.rsplit("/", 1)[-1]
        dot = basename.rfind(".")
        extension = basename[dot:] if dot >= 0 else ""
        if extension in _CODE_EXTENSIONS:
            code_files.append(path)

        if basename in _PACKAGE_CONFIG_NAMES:
            package_configs.append(path)

        if (
            basename in _DEPLOYMENT_FILE_NAMES
            or lower_path.startswith(("deploy/", "deployment/", "k8s/", "kubernetes/", "helm/", "charts/"))
        ):
            deployment_files.append(path)

        if (
            lower_path.startswith(("tests/", "test/", "__tests__/"))
            or "/tests/" in lower_path
            or "/test/" in lower_path
            or basename.startswith("test_")
            or basename.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
        ):
            test_files.append(path)

        if lower_path.startswith(".github/workflows/") or basename in {
            ".gitlab-ci.yml", "circle.yml", "jenkinsfile",
        }:
            ci_files.append(path)

    return {
        "engineering_tree_evidence": True,
        "repo_file_count": len(files),
        "repo_code_file_count": len(code_files),
        "package_config_files": package_configs[:8],
        "deployment_files": deployment_files[:8],
        "test_files": test_files[:8],
        "ci_files": ci_files[:8],
    }


def _attach_engineering_tree_metrics(record: dict, paths) -> dict:
    metrics = record.get("metrics") or {}
    metrics.update(_engineering_tree_profile(paths))
    record["metrics"] = metrics
    return record


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
            "engineering_tree_evidence": False,
            "repo_file_count": 0,
            "repo_code_file_count": 0,
            "package_config_files": [],
            "deployment_files": [],
            "test_files": [],
            "ci_files": [],
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
        search_successes = 0
        search_failures = []

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
                    search_failures.append(f"{search_term}:返回格式无效")
                    logger.warning("GitHub 接口返回数据格式无效：查询=%s", search_term)
                    continue
                items = payload.get("items")
                if not isinstance(items, list):
                    search_failures.append(f"{search_term}:缺少items")
                    logger.warning("GitHub 接口返回内容缺少 items：查询=%s", search_term)
                    continue

                search_successes += 1
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("id") or item.get("html_url")
                    if key:
                        candidates[key] = item
            except Exception as error:
                search_failures.append(f"{search_term}:{type(error).__name__}")
                logger.exception("GitHub 搜索失败：查询=%s", search_term)
                continue

        if search_successes == 0:
            raise RuntimeError(
                f"GitHub 所有搜索查询均失败：0/{len(SEARCH_TERMS)} 成功，本轮不能视为成功空结果"
            )

        if search_failures:
            self.collection_partial = True
            self.collection_partial_reason = (
                f"GitHub 搜索覆盖部分降级：成功 {search_successes}/{len(SEARCH_TERMS)}，"
                f"失败 {len(search_failures)}"
            )
            logger.warning(
                "%s 失败查询=%s",
                self.collection_partial_reason,
                search_failures[:5],
            )

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
        tree_attempted = 0
        tree_enriched = 0

        for record, raw in preliminary:
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

            # 只对已经通过商业许可和业务资格 Gate 的前若干仓库读取文件树，控制 GitHub API 预算。
            # 文件树是额外增强：请求失败时保留原有成熟度逻辑；请求成功时用真实代码/配置/测试证据加强 Gate。
            if tree_attempted < ENGINEERING_TREE_ENRICH_LIMIT:
                tree_attempted += 1
                full_name = str(raw.get("full_name") or "").strip()
                default_branch = str(raw.get("default_branch") or "").strip()
                paths = _fetch_engineering_tree(full_name, default_branch, headers)
                if paths is not None:
                    _attach_engineering_tree_metrics(record, paths)
                    tree_enriched += 1

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
            "GitHub 近期候选=%s 搜索成功=%s/%s README增强=%s 文件树增强=%s/%s 许可淘汰=%s 资格淘汰=%s 部署淘汰=%s 合格=%s 最终返回=%s",
            len(candidates),
            search_successes,
            len(SEARCH_TERMS),
            enriched,
            tree_enriched,
            tree_attempted,
            license_rejected,
            rejected,
            deployment_rejected,
            len(result),
            min(len(result), limit),
        )
        return result[:limit]


def fetch_ai_repositories(limit: int = 15):
    return GithubCollector().collect_safe(limit)
from datetime import datetime, timezone
from typing import Dict


RECENT_COMMIT_WINDOW_DAYS = 14


def _number(value) -> float:
    try:
        return max(float(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _parse_time(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _list_metric(metrics: dict, key: str) -> list:
    value = metrics.get(key) or []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def github_activity_profile(item: Dict, *, now: datetime | None = None) -> Dict:
    """评价 GitHub 仓库的版本/提交/可安装工程成熟度，不替代业务与许可 Gate。"""
    metrics = item.get("metrics") if isinstance(item, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    release_tag = str(metrics.get("latest_release_tag") or "").strip()
    release_published = _parse_time(metrics.get("latest_release_published_at"))
    commit_checked = bool(metrics.get("recent_commit_activity_checked"))
    commit_count = int(_number(metrics.get("recent_commit_sample_count")))
    package_configs = _list_metric(metrics, "package_config_files")
    deployment_files = _list_metric(metrics, "deployment_files")
    test_files = _list_metric(metrics, "test_files")
    ci_files = _list_metric(metrics, "ci_files")

    score = 0
    evidence = []

    if release_tag:
        score += 24
        evidence.append(f"正式Release:{release_tag}")
        if release_published is not None:
            release_age_days = max((now - release_published).total_seconds() / 86400, 0)
            if release_age_days <= 30:
                score += 10
                evidence.append("Release近30天")
            elif release_age_days <= 90:
                score += 6
                evidence.append("Release近90天")

    if commit_checked:
        if commit_count >= 8:
            score += 24
        elif commit_count >= 5:
            score += 19
        elif commit_count >= 2:
            score += 11
        elif commit_count == 1:
            score += 5
        if commit_count:
            evidence.append(
                f"近{int(metrics.get('recent_commit_window_days') or RECENT_COMMIT_WINDOW_DAYS)}天提交样本:{commit_count}"
            )
        else:
            evidence.append(
                f"近{int(metrics.get('recent_commit_window_days') or RECENT_COMMIT_WINDOW_DAYS)}天默认分支未发现提交"
            )

    if package_configs:
        score += 16
        evidence.append("可安装/构建:" + "/".join(package_configs[:3]))
    if deployment_files:
        score += 12
        evidence.append("可部署资产:" + "/".join(deployment_files[:3]))
    if test_files:
        score += 7
        evidence.append("测试资产:存在")
    if ci_files:
        score += 7
        evidence.append("CI资产:存在")

    return {
        "score": min(score, 100),
        "evidence": evidence,
        "has_release": bool(release_tag),
        "recent_commit_sample_count": commit_count,
    }


def attach_github_activity_metrics(item: Dict) -> Dict:
    """把版本与提交成熟度写入 metrics，并前置到 DeepSeek 可见证据。"""
    item = item if isinstance(item, dict) else {}
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics

    profile = github_activity_profile(item)
    metrics["github_activity_score"] = int(profile["score"])
    metrics["github_activity_evidence"] = list(profile["evidence"])

    current = metrics.get("opportunity_evidence") or []
    current = list(current) if isinstance(current, list) else []
    current = [
        value
        for value in current
        if not str(value).startswith("GitHub工程:")
    ]
    activity_evidence = [f"GitHub工程:{value}" for value in profile["evidence"]]
    metrics["opportunity_evidence"] = activity_evidence + current
    return item

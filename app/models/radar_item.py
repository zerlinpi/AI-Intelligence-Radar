from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def _serialized_metrics(value: Dict[str, Any]) -> Dict[str, Any]:
    """序列化前恢复产品决策所需证据，避免中间筛选步骤覆盖证据列表。

    relevance/scoring 会重新生成 opportunity_evidence；商业许可、部署成熟度和 GitHub
    版本/提交活动则保存在独立 metrics 字段中。这里在统一出口重新合并，使 DeepSeek、
    数据库和后续报告都能读取完整证据。
    """
    metrics = dict(value or {})
    raw_evidence = metrics.get("opportunity_evidence") or []
    evidence = list(raw_evidence) if isinstance(raw_evidence, list) else []

    def prepend(prefix: str, text: str):
        text = " ".join(str(text or "").split()).strip()
        if not text:
            return
        line = f"{prefix}:{text}"
        evidence[:] = [item for item in evidence if not str(item).startswith(f"{prefix}:")]
        evidence.insert(0, line)

    deployment_reason = metrics.get("deployment_readiness_reason")
    if deployment_reason:
        prepend("部署成熟度", deployment_reason)

    deployment_details = metrics.get("deployment_evidence") or []
    if isinstance(deployment_details, list):
        details = [
            " ".join(str(value or "").split()).strip()
            for value in deployment_details
            if str(value or "").strip()
        ]
        if details:
            # 合并成一个证据槽，避免 analyzer 的前5条证据预算被工程细节全部占满。
            prepend("部署证据", "/".join(details[:4]))

    # Release、默认分支真实提交、package/deploy/test/CI 在 collector 中单独持久化。
    # scoring 即使刷新 opportunity_evidence，这个独立字段仍可在进入 DeepSeek 前恢复。
    github_activity = metrics.get("github_activity_evidence") or []
    if isinstance(github_activity, list):
        activity_details = [
            " ".join(str(value or "").split()).strip()
            for value in github_activity
            if str(value or "").strip()
        ]
        if activity_details:
            prepend("GitHub工程", "/".join(activity_details[:5]))

    license_reason = metrics.get("commercial_readiness_reason")
    if license_reason:
        prepend("商业许可", license_reason)

    history_reason = metrics.get("history_material_update_reason")
    if history_reason and not any(str(item).startswith("重大更新:") for item in evidence):
        prepend("重大更新", history_reason)

    if evidence:
        metrics["opportunity_evidence"] = evidence
    return metrics


@dataclass
class RadarItem:
    """Unified intelligence object used across collectors, scoring and AI analysis."""

    title: str
    source: str
    url: str = ""
    description: str = ""
    category: str = "ai"

    metrics: Dict[str, Any] = field(default_factory=dict)

    created_at: Optional[datetime] = None
    trend_score: float = 0

    analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        metrics = _serialized_metrics(self.metrics)
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "metrics": metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "trend_score": self.trend_score,
            "analysis": self.analysis,
            **metrics,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        data = data or {}
        metrics = dict(data.get("metrics") or {})

        for key in ["stars", "forks", "comments", "downloads", "upvotes"]:
            if key in data:
                metrics[key] = data[key]

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None

        return cls(
            title=data.get("title", data.get("name", "Unknown")),
            source=data.get("source", "unknown"),
            url=data.get("url", ""),
            description=data.get("description", "") or "",
            category=data.get("category", "ai"),
            metrics=metrics,
            created_at=created_at,
            trend_score=data.get("trend_score", 0) or 0,
            analysis=data.get("analysis") or {},
        )

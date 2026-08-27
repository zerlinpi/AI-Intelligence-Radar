from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def _serialized_metrics(value: Dict[str, Any]) -> Dict[str, Any]:
    """序列化前恢复产品决策所需证据，避免中间筛选步骤覆盖证据列表。

    relevance 会重新生成 opportunity_evidence；商业许可和部署成熟度则保存在独立 metrics
    字段中。这里在统一出口重新合并，使 DeepSeek、数据库和后续报告都能读取完整证据。
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

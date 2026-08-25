from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


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
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "trend_score": self.trend_score,
            "analysis": self.analysis,
            **self.metrics,
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

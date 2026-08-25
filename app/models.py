from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RadarItem:
    source: str
    title: str
    url: str = ""
    description: str = ""
    stars: int = 0
    forks: int = 0
    comments: int = 0
    downloads: int = 0
    upvotes: int = 0
    published_at: str | None = None
    collected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    trend_score: float = 0
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return self.__dict__

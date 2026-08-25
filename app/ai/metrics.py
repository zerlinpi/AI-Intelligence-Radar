from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class LLMCallMetric:
    provider: str
    model: str
    success: bool
    latency: float
    attempt: int
    tokens: Optional[int] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return asdict(self)


def build_llm_metric(
    provider: str,
    model: str,
    result: dict,
    tokens: Optional[int] = None,
) -> dict:
    """Create a normalized LLM usage metric."""
    return LLMCallMetric(
        provider=provider,
        model=model,
        success=result.get("success", False),
        latency=result.get("latency", 0),
        attempt=result.get("attempt", 0),
        tokens=tokens,
    ).to_dict()

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ActionItem:
    label: str
    text: str


@dataclass
class DailySummary:
    date_text: str
    judgment: str
    actions: List[ActionItem] = field(default_factory=list)
    metrics: Dict[str, int] = field(default_factory=dict)


@dataclass
class ComplianceDecision:
    focus: str
    title: str
    source_name: str
    authority: str = ""
    kind: str = ""
    age_text: str = ""
    url: str = ""
    risk_level: str = "medium"
    impact_score: float = 50
    requirement: str = ""
    impact: str = ""
    affected_products: str = ""
    risk: str = ""
    preparation: str = ""
    action: str = ""


@dataclass
class ProductDecision:
    title: str
    source_name: str
    age_text: str = ""
    url: str = ""
    trend_score: float = 0
    business_score: float = 0
    opportunity: str = "medium"
    tags: List[str] = field(default_factory=list)
    description: str = ""
    growth_signal: str = ""
    judgment: str = ""
    direction: str = ""
    cross_border: bool = False


@dataclass
class ReportDecisionModel:
    summary: DailySummary
    compliance: List[ComplianceDecision] = field(default_factory=list)
    products: List[ProductDecision] = field(default_factory=list)


@dataclass
class CardEnvelope:
    card_type: str
    payload: Dict
    fallback_text: str

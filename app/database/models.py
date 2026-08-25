from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Text, DateTime, JSON, Index


class Base(DeclarativeBase):
    pass


class IntelligenceItem(Base):
    __tablename__ = "intelligence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)

    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="ai")

    trend_score: Mapped[float] = mapped_column(Float, default=0)
    business_score: Mapped[float] = mapped_column(Float, default=0)

    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )


Index(
    "idx_intelligence_source_score",
    IntelligenceItem.source,
    IntelligenceItem.trend_score,
)

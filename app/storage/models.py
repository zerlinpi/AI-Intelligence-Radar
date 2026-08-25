from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, UniqueConstraint

from app.storage.database import Base


class RadarRecord(Base):
    __tablename__ = "radar_records"

    id = Column(Integer, primary_key=True)
    url = Column(String(500), nullable=False)
    source = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    trend_score = Column(Float, default=0)
    analysis = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("url", name="uq_radar_url"),
    )

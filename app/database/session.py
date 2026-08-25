from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base

DATABASE_URL = "sqlite:///./radar.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_database():
    Base.metadata.create_all(engine)

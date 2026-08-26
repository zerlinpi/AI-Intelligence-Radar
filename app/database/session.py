import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/radar.db")


def _prepare_sqlite_directory(database_url: str) -> None:
    """Ensure the parent directory exists for file-backed SQLite databases."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return

    database_path = database_url[len(prefix):]
    if not database_path or database_path == ":memory:":
        return

    parent = os.path.dirname(os.path.abspath(database_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


_prepare_sqlite_directory(DATABASE_URL)

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite:")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@contextmanager
def get_session():
    """Provide a managed database session."""
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database():
    Base.metadata.create_all(engine)

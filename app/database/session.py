import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
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
    {
        "check_same_thread": False,
        # SQLite 原生等待时间，避免极短写锁直接变成 database is locked。
        "timeout": 15,
    }
    if DATABASE_URL.startswith("sqlite:")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


if DATABASE_URL.startswith("sqlite:"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        """为长驻 Docker 进程启用更稳的 SQLite 参数。"""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            # WAL 可显著减少读写互相阻塞；内存数据库会自动保持其支持的模式。
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
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
    """初始化表结构，并在文件型 SQLite 进入本轮写入前创建一致性备份。"""
    Base.metadata.create_all(engine)

    # 延迟导入避免数据库模块加载阶段形成循环依赖。
    from app.database.backup import backup_database

    return backup_database()

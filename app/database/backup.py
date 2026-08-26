import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import DATABASE_BACKUP_DIR, DATABASE_BACKUP_RETENTION, DATABASE_URL
from app.core.logger import get_logger


logger = get_logger("数据库备份")
_SQLITE_PREFIX = "sqlite:///"


def sqlite_database_path() -> Optional[Path]:
    """返回文件型 SQLite 数据库路径；内存库或其他数据库返回 None。"""
    value = str(DATABASE_URL or "")
    if not value.startswith(_SQLITE_PREFIX):
        return None

    raw_path = value[len(_SQLITE_PREFIX):]
    if not raw_path or raw_path == ":memory:":
        return None
    return Path(raw_path).expanduser().resolve()


def _backup_dir() -> Path:
    path = Path(DATABASE_BACKUP_DIR).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prune_backups(directory: Path) -> None:
    keep = max(int(DATABASE_BACKUP_RETENTION or 1), 1)
    backups = sorted(
        (path for path in directory.glob("radar-*.db") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[keep:]:
        stale.unlink(missing_ok=True)


def backup_database() -> Optional[Path]:
    """使用 SQLite backup API 创建一致性在线备份，并自动清理旧备份。"""
    source_path = sqlite_database_path()
    if source_path is None or not source_path.exists():
        return None

    directory = _backup_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = directory / f"radar-{timestamp}.db"

    source = sqlite3.connect(str(source_path), timeout=15)
    target = sqlite3.connect(str(destination), timeout=15)
    try:
        source.backup(target)
        row = target.execute("PRAGMA quick_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError(f"备份完整性检查失败：{row}")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        target.close()
        source.close()

    _prune_backups(directory)
    logger.info("SQLite 在线备份完成：%s", destination)
    return destination


def list_backups():
    directory = _backup_dir()
    return sorted(
        (path for path in directory.glob("radar-*.db") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

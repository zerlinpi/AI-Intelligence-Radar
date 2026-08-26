"""
SQLite 数据库结构迁移工具。

新安装时创建基础结构，已有安装则补充缺失字段。
"""

import os
import sqlite3


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS intelligence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255) NOT NULL DEFAULT '',
    url TEXT DEFAULT '',
    source VARCHAR(50) DEFAULT '',
    description TEXT DEFAULT '',
    trend_score REAL DEFAULT 0,
    business_score REAL DEFAULT 0,
    created_at DATETIME,
    category VARCHAR(50) DEFAULT 'ai',
    metrics JSON DEFAULT '{}',
    analysis JSON DEFAULT '{}'
)
"""


MIGRATIONS = [
    (
        "category",
        "ALTER TABLE intelligence_items ADD COLUMN category VARCHAR(50) DEFAULT 'ai'",
    ),
    (
        "business_score",
        "ALTER TABLE intelligence_items ADD COLUMN business_score REAL DEFAULT 0",
    ),
    (
        "metrics",
        "ALTER TABLE intelligence_items ADD COLUMN metrics JSON DEFAULT '{}'",
    ),
    (
        "analysis",
        "ALTER TABLE intelligence_items ADD COLUMN analysis JSON DEFAULT '{}'",
    ),
]


def resolve_database_path() -> str:
    """解析与主程序一致的 SQLite 文件路径。"""
    sqlite_path = (os.getenv("SQLITE_PATH") or "").strip()
    if sqlite_path:
        return sqlite_path

    database_url = (
        os.getenv("DATABASE_URL") or "sqlite:///./data/radar.db"
    ).strip()
    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise RuntimeError(
            "数据库迁移脚本当前仅支持 SQLite；请将 DATABASE_URL 配置为 "
            "sqlite:/// 地址，或提供 SQLITE_PATH。"
        )

    database_path = database_url[len(prefix):]
    if not database_path or database_path == ":memory:":
        raise RuntimeError("数据库迁移需要使用文件形式的 SQLite 数据库。")

    return database_path


def migrate(database_path: str):
    parent = os.path.dirname(os.path.abspath(database_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(database_path)
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE)

        cursor.execute("PRAGMA table_info(intelligence_items)")
        existing = {row[1] for row in cursor.fetchall()}

        for column, sql in MIGRATIONS:
            if column not in existing:
                cursor.execute(sql)

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = resolve_database_path()
    migrate(db_path)
    print(f"数据库迁移完成：{db_path}")

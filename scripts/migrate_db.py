"""
SQLite schema migration helper.

Creates the base schema for fresh installations and applies
incremental migrations for upgraded installations.
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
    """Resolve the same file-backed SQLite database used by the application."""
    sqlite_path = (os.getenv("SQLITE_PATH") or "").strip()
    if sqlite_path:
        return sqlite_path

    database_url = (
        os.getenv("DATABASE_URL") or "sqlite:///./data/radar.db"
    ).strip()
    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise RuntimeError(
            "scripts/migrate_db.py supports SQLite only; "
            "set DATABASE_URL to a sqlite:/// URL or provide SQLITE_PATH."
        )

    database_path = database_url[len(prefix):]
    if not database_path or database_path == ":memory:":
        raise RuntimeError("A file-backed SQLite database is required for migration.")

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
    print(f"Database migration completed: {db_path}")

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
    trend_score INTEGER DEFAULT 0,
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
        "metrics",
        "ALTER TABLE intelligence_items ADD COLUMN metrics JSON DEFAULT '{}'",
    ),
    (
        "analysis",
        "ALTER TABLE intelligence_items ADD COLUMN analysis JSON DEFAULT '{}'",
    ),
]


def migrate(database_path: str):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    cursor.execute(CREATE_TABLE)

    cursor.execute("PRAGMA table_info(intelligence_items)")
    existing = {row[1] for row in cursor.fetchall()}

    for column, sql in MIGRATIONS:
        if column not in existing:
            cursor.execute(sql)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    db_path = os.getenv("SQLITE_PATH", "radar.db")
    migrate(db_path)
    print("Database migration completed")

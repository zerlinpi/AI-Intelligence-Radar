"""
SQLite schema migration helper.

Adds columns introduced by RadarItem persistence upgrades when an existing
installation is upgraded from an older database.
"""

import os
import sqlite3


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

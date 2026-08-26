import sqlite3

from app.database import backup


def _create_database(path):
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO demo(value) VALUES ('ok')")
        connection.commit()
    finally:
        connection.close()


def test_sqlite_backup_is_consistent_and_restorable(tmp_path, monkeypatch):
    source = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    _create_database(source)

    monkeypatch.setattr(backup, "DATABASE_URL", f"sqlite:///{source}")
    monkeypatch.setattr(backup, "DATABASE_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup, "DATABASE_BACKUP_RETENTION", 7)

    backup_path = backup.backup_database()
    assert backup_path is not None
    assert backup_path.exists()

    connection = sqlite3.connect(str(backup_path))
    try:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM demo").fetchone()[0] == "ok"
    finally:
        connection.close()


def test_sqlite_backup_prunes_old_files(tmp_path, monkeypatch):
    source = tmp_path / "radar.db"
    backup_dir = tmp_path / "backups"
    _create_database(source)

    monkeypatch.setattr(backup, "DATABASE_URL", f"sqlite:///{source}")
    monkeypatch.setattr(backup, "DATABASE_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup, "DATABASE_BACKUP_RETENTION", 2)

    for _ in range(4):
        backup.backup_database()

    assert len(backup.list_backups()) == 2


def test_non_file_database_does_not_create_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setattr(backup, "DATABASE_BACKUP_DIR", str(tmp_path / "backups"))
    assert backup.backup_database() is None

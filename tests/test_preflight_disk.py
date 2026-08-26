from collections import namedtuple

from app.core import preflight


DiskUsage = namedtuple("DiskUsage", "total used free")


def test_disk_space_check_blocks_low_free_space(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "FEISHU_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(preflight, "DATA_MIN_FREE_MB", 256)
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _path: DiskUsage(1024**3, 1024**3 - 100 * 1024**2, 100 * 1024**2),
    )

    result = preflight._disk_space_check()
    assert result.ok is False
    assert "100 MB" in result.detail


def test_disk_space_check_passes_with_safe_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "FEISHU_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(preflight, "DATA_MIN_FREE_MB", 256)
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _path: DiskUsage(1024**3, 400 * 1024**2, 624 * 1024**2),
    )

    result = preflight._disk_space_check()
    assert result.ok is True
    assert "624 MB" in result.detail

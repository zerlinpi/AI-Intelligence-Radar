import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "send_chatgpt_feed.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("send_chatgpt_feed_test_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_same_day_success_is_deduplicated(monkeypatch, tmp_path):
    module = _load_module()
    status_path = tmp_path / "chatgpt-feed-status.json"
    status_path.write_text(
        json.dumps(
            {
                "date": "2026-09-30",
                "sent": True,
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "STATUS_PATH", status_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-09-30")

    called = {"fetch": 0}

    def fail_if_called(*args, **kwargs):
        called["fetch"] += 1
        raise AssertionError("dedupe must happen before fetching the feed")

    monkeypatch.setattr(module, "fetch_latest_report", fail_if_called)

    assert module.main() == 0
    assert called["fetch"] == 0


def test_missing_feed_sends_direct_feishu_alert(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "STATUS_PATH", tmp_path / "chatgpt-feed-status.json")
    monkeypatch.setenv("GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-09-30")

    def missing(*args, **kwargs):
        raise module.MissingFeedError("missing")

    alerts = []
    monkeypatch.setattr(module, "fetch_latest_report", missing)
    monkeypatch.setattr(module, "send_feishu", lambda text: alerts.append(text) or True)

    assert module.main() == 1
    status = json.loads(module.STATUS_PATH.read_text(encoding="utf-8"))
    assert status["status"] == "missing_feed"
    assert status["sent"] is False
    assert status["alert_sent"] is True
    assert alerts
    assert "2026-09-30" in alerts[0]
    assert "Feed" in alerts[0]

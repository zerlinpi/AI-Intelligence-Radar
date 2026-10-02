import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "send_chatgpt_feed.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("send_chatgpt_feed_test_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _feed_body(date_text: str) -> str:
    return (
        "AI-INTELLIGENCE-RADAR-CHATGPT-FEED\n\n"
        "~~~json\n"
        + json.dumps({"date_text": date_text})
        + "\n~~~"
    ).replace("~~~", "```")


def _receipt_body(date_text: str) -> str:
    return (
        "AI-INTELLIGENCE-RADAR-DELIVERED\n\n"
        "~~~json\n"
        + json.dumps({"date_text": date_text, "cards": 3})
        + "\n~~~"
    ).replace("~~~", "```")


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
    monkeypatch.setenv("CHATGPT_FEED_AUTHOR", "zerlinpi")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-09-30")

    called = {"fetch": 0}

    def fail_if_called(*args, **kwargs):
        called["fetch"] += 1
        raise AssertionError("dedupe must happen before fetching the feed")

    monkeypatch.setattr(module, "fetch_issue_comments", fail_if_called)

    assert module.main() == 0
    assert called["fetch"] == 0


def test_missing_feed_sends_direct_feishu_alert(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "STATUS_PATH", tmp_path / "chatgpt-feed-status.json")
    monkeypatch.setenv("GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CHATGPT_FEED_AUTHOR", "zerlinpi")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-09-30")
    monkeypatch.setattr(module, "fetch_issue_comments", lambda **kwargs: [])

    alerts = []
    monkeypatch.setattr(module, "send_feishu", lambda text: alerts.append(text) or True)

    assert module.main() == 1
    status = json.loads(module.STATUS_PATH.read_text(encoding="utf-8"))
    assert status["status"] == "missing_feed"
    assert status["sent"] is False
    assert status["alert_sent"] is True
    assert alerts
    assert "2026-09-30" in alerts[0]
    assert "Feed" in alerts[0]


def test_untrusted_feed_comment_is_ignored():
    module = _load_module()
    comments = [
        {
            "id": 10,
            "user": {"login": "attacker"},
            "body": _feed_body("2026-09-30"),
        },
        {
            "id": 9,
            "user": {"login": "zerlinpi"},
            "body": _feed_body("2026-09-29"),
        },
    ]

    with pytest.raises(module.MissingFeedError):
        module.find_latest_report(comments, "2026-09-30", "zerlinpi")


def test_trusted_feed_comment_is_selected():
    module = _load_module()
    comments = [
        {
            "id": 10,
            "user": {"login": "attacker"},
            "body": _feed_body("2026-09-30"),
        },
        {
            "id": 11,
            "user": {"login": "zerlinpi"},
            "body": _feed_body("2026-09-30"),
        },
    ]

    payload, comment_id = module.find_latest_report(
        comments,
        "2026-09-30",
        "zerlinpi",
    )
    assert payload["date_text"] == "2026-09-30"
    assert comment_id == 11


def test_fake_delivery_receipt_does_not_suppress_send():
    module = _load_module()
    comments = [
        {
            "id": 12,
            "user": {"login": "attacker"},
            "body": _receipt_body("2026-09-30"),
        }
    ]
    assert module.has_delivery_receipt(comments, "2026-09-30", "zerlinpi") is False


def test_github_actions_delivery_receipt_deduplicates():
    module = _load_module()
    comments = [
        {
            "id": 13,
            "user": {"login": "github-actions[bot]"},
            "body": _receipt_body("2026-09-30"),
        }
    ]
    assert module.has_delivery_receipt(comments, "2026-09-30", "zerlinpi") is True


def test_issue_comment_fetch_paginates_past_first_100(monkeypatch):
    module = _load_module()
    pages = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    first = [{"id": value} for value in range(1, 101)]
    second = [{"id": 101}]

    def fake_get(*args, **kwargs):
        page = kwargs["params"]["page"]
        pages.append(page)
        return Response(first if page == 1 else second)

    monkeypatch.setattr(module.requests, "get", fake_get)

    comments = module.fetch_issue_comments(
        repository="zerlinpi/AI-Intelligence-Radar",
        issue_number=2,
        token="test-token",
    )
    assert len(comments) == 101
    assert pages == [1, 2]


def test_send_window_accepts_0800_and_rejects_afternoon(monkeypatch):
    module = _load_module()
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setenv("RADAR_SEND_WINDOW_START", "08:00")
    monkeypatch.setenv("RADAR_SEND_WINDOW_END", "08:10")
    tz = ZoneInfo("Asia/Shanghai")

    assert module._send_window_state(datetime(2026, 10, 3, 8, 0, 0, tzinfo=tz)) == "open"
    assert module._send_window_state(datetime(2026, 10, 3, 8, 9, 59, tzinfo=tz)) == "open"
    assert module._send_window_state(datetime(2026, 10, 3, 8, 10, 0, tzinfo=tz)) == "late"
    assert module._send_window_state(datetime(2026, 10, 3, 15, 0, 0, tzinfo=tz)) == "late"


def test_late_run_never_calls_github_or_feishu(monkeypatch, tmp_path):
    module = _load_module()
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(module, "STATUS_PATH", tmp_path / "chatgpt-feed-status.json")
    monkeypatch.setenv("GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CHATGPT_FEED_AUTHOR", "zerlinpi")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-10-03")
    monkeypatch.setenv("RADAR_ENFORCE_SEND_WINDOW", "1")
    monkeypatch.setenv("RADAR_SEND_WINDOW_START", "08:00")
    monkeypatch.setenv("RADAR_SEND_WINDOW_END", "08:10")

    monkeypatch.setattr(module, "_send_window_state", lambda now=None: "late")

    called = {"github": 0, "feishu": 0}

    def github_should_not_run(**kwargs):
        called["github"] += 1
        raise AssertionError("late run must not fetch Feed")

    def feishu_should_not_run(*args, **kwargs):
        called["feishu"] += 1
        raise AssertionError("late run must not send Feishu")

    monkeypatch.setattr(module, "fetch_issue_comments", github_should_not_run)
    monkeypatch.setattr(module, "send_feishu", feishu_should_not_run)
    monkeypatch.setattr(module, "send_feishu_cards", feishu_should_not_run)

    assert module.main() == 2
    assert called == {"github": 0, "feishu": 0}
    status = json.loads(module.STATUS_PATH.read_text(encoding="utf-8"))
    assert status["status"] == "outside_send_window"
    assert status["window_state"] == "late"

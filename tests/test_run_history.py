from app.core import run_history


def test_run_history_records_lightweight_summary(tmp_path, monkeypatch):
    history_file = tmp_path / "run-history.json"
    monkeypatch.setattr(run_history, "RUN_HISTORY_FILE", str(history_file))
    monkeypatch.setattr(run_history, "RUN_HISTORY_LIMIT", 10)

    row = run_history.record_run(
        {
            "execution_id": "run-1",
            "time": "2026-08-26T12:00:00+00:00",
            "duration": 12.5,
            "status": "success",
            "items": [{"title": "secret-project", "url": "https://example.com/private"}],
            "policies": [{"title": "policy"}],
            "feishu_cards": 3,
            "feishu_sent": True,
            "errors": [],
        }
    )

    assert row["item_count"] == 1
    assert row["policy_count"] == 1
    assert row["saved_count"] == 2
    assert row["feishu_sent"] is True
    assert "secret-project" not in history_file.read_text(encoding="utf-8")
    assert "example.com/private" not in history_file.read_text(encoding="utf-8")
    assert run_history.latest_run()["execution_id"] == "run-1"


def test_run_history_infers_ai_fallback_count(tmp_path, monkeypatch):
    monkeypatch.setattr(run_history, "RUN_HISTORY_FILE", str(tmp_path / "history.json"))

    row = run_history.record_run(
        {
            "execution_id": "run-2",
            "status": "partial",
            "items": [{}, {}, {}],
            "policies": [{}],
            "errors": ["AI 分析降级 2 条"],
        }
    )

    assert row["ai_fallbacks"] == 2
    assert row["saved_count"] == 2


def test_run_history_keeps_recent_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(run_history, "RUN_HISTORY_FILE", str(tmp_path / "history.json"))
    monkeypatch.setattr(run_history, "RUN_HISTORY_LIMIT", 10)

    for index in range(15):
        run_history.record_run({"execution_id": f"run-{index}", "status": "success"})

    rows = run_history.recent_runs(limit=20)
    assert len(rows) == 10
    assert rows[0]["execution_id"] == "run-14"
    assert rows[-1]["execution_id"] == "run-5"

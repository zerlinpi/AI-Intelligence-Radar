from types import SimpleNamespace

from app import main


def _preflight(ok=True, failures=None):
    return SimpleNamespace(ok=ok, failures=list(failures or []))


def test_readiness_returns_503_when_scheduler_is_stopped(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=False))
    monkeypatch.setattr(main, "run_preflight", lambda: _preflight(True))

    response = main.readiness_check()

    assert response.status_code == 503
    assert '"就绪":false'.encode("utf-8") in response.body


def test_readiness_returns_503_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(
        main,
        "run_preflight",
        lambda: _preflight(False, ["模型密钥"]),
    )

    response = main.readiness_check()

    assert response.status_code == 503
    assert '"预检通过":false'.encode("utf-8") in response.body
    assert "模型密钥".encode("utf-8") in response.body


def test_readiness_returns_200_when_scheduler_and_preflight_are_ready(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "run_preflight", lambda: _preflight(True))

    response = main.readiness_check()

    assert response.status_code == 200
    assert '"就绪":true'.encode("utf-8") in response.body


def test_run_returns_503_when_central_pipeline_reports_preflight_failure(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_daily_radar",
        lambda: {
            "execution_id": "run-preflight",
            "status": "failed",
            "errors": ["生产预检失败：数据库"],
            "items": [],
            "policies": [],
        },
    )
    recorded = []
    monkeypatch.setattr(main, "record_run_safe", lambda result: recorded.append(result))

    response = main.run()
    assert response.status_code == 503
    assert "数据库".encode("utf-8") in response.body
    assert recorded and recorded[0]["execution_id"] == "run-preflight"


def test_runtime_status_is_lightweight(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "latest_run", lambda: {"execution_id": "run-1", "status": "success"})
    monkeypatch.setattr(main, "list_pending", lambda: ["a.json", "b.json"])
    monkeypatch.setattr(main, "list_backups", lambda: ["backup.db"])

    result = main.runtime_status()
    assert result["调度器运行中"] is True
    assert result["最近执行"]["execution_id"] == "run-1"
    assert result["飞书待补发队列"] == 2
    assert result["数据库备份数量"] == 1


def test_home_uses_chinese_public_fields():
    result = main.home()

    assert result["名称"] == "AI 情报雷达"
    assert result["状态"] == "运行中"

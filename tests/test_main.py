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


def test_run_rejects_execution_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_preflight",
        lambda: _preflight(False, ["数据库"]),
    )
    monkeypatch.setattr(
        main,
        "run_daily_radar",
        lambda: (_ for _ in ()).throw(AssertionError("不应执行日报")),
    )

    response = main.run()
    assert response.status_code == 503
    assert "数据库".encode("utf-8") in response.body


def test_home_uses_chinese_public_fields():
    result = main.home()

    assert result["名称"] == "AI 情报雷达"
    assert result["状态"] == "运行中"

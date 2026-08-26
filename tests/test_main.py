from types import SimpleNamespace

from app import main


def test_readiness_returns_503_when_scheduler_is_stopped(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=False))

    response = main.readiness_check()

    assert response.status_code == 503
    assert '"就绪":false'.encode("utf-8") in response.body


def test_readiness_returns_200_when_scheduler_is_running(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))

    response = main.readiness_check()

    assert response.status_code == 200
    assert '"就绪":true'.encode("utf-8") in response.body


def test_home_uses_chinese_public_fields():
    result = main.home()

    assert result["名称"] == "AI 情报雷达"
    assert result["状态"] == "运行中"

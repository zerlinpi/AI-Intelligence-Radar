from types import SimpleNamespace

from app import main


def test_readiness_returns_503_when_scheduler_is_stopped(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=False))

    response = main.readiness_check()

    assert response.status_code == 503
    assert b'"ready":false' in response.body


def test_readiness_returns_200_when_scheduler_is_running(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))

    response = main.readiness_check()

    assert response.status_code == 200
    assert b'"ready":true' in response.body

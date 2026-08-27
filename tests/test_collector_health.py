import requests

from app.sources import base
from app.sources.base import BaseCollector


class _TransientCollector(BaseCollector):
    name = "transient"

    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        if self.calls == 1:
            raise requests.ConnectionError("temporary network failure")
        return [{"title": "recovered"}]


class _EmptyCollector(BaseCollector):
    name = "empty"

    def collect(self):
        return []


class _BrokenCollector(BaseCollector):
    name = "broken"

    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        raise ValueError("deterministic parser bug")


class _RateLimitedCollector(BaseCollector):
    name = "rate-limit"

    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        if self.calls == 1:
            response = requests.Response()
            response.status_code = 429
            error = requests.HTTPError("rate limited", response=response)
            raise error
        return [{"title": "after retry"}]


def test_transient_network_failure_retries_once_and_records_health(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    collector = _TransientCollector()

    result = collector.collect_safe()
    health = collector.get_last_health()

    assert result == [{"title": "recovered"}]
    assert collector.calls == 2
    assert health["success"] is True
    assert health["attempts"] == 2
    assert health["result_count"] == 1
    assert health["error"] == ""


def test_empty_result_is_success_not_failure():
    collector = _EmptyCollector()

    assert collector.collect_safe() == []
    health = collector.get_last_health()

    assert health["success"] is True
    assert health["attempts"] == 1
    assert health["result_count"] == 0


def test_deterministic_error_fails_fast_without_blind_retry(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    collector = _BrokenCollector()

    assert collector.collect_safe() == []
    health = collector.get_last_health()

    assert collector.calls == 1
    assert health["success"] is False
    assert health["attempts"] == 1
    assert "ValueError" in health["error"]


def test_http_429_is_retried(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    collector = _RateLimitedCollector()

    result = collector.collect_safe()
    health = collector.get_last_health()

    assert result == [{"title": "after retry"}]
    assert collector.calls == 2
    assert health["success"] is True
    assert health["attempts"] == 2

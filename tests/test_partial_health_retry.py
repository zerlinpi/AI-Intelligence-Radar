import requests

from app.sources import base
from app.sources.base import BaseCollector


class _PartialThenRecoveredCollector(BaseCollector):
    name = "partial-then-recovered"

    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        if self.calls == 1:
            self.collection_partial = True
            self.collection_partial_reason = "first attempt only"
            raise requests.ConnectionError("temporary failure after partial response")
        return [{"title": "fully recovered"}]


def test_retry_does_not_inherit_partial_state_from_failed_attempt(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    collector = _PartialThenRecoveredCollector()

    result = collector.collect_safe()
    health = collector.get_last_health()

    assert result == [{"title": "fully recovered"}]
    assert collector.calls == 2
    assert health["success"] is True
    assert health["attempts"] == 2
    assert health["partial"] is False
    assert health["error"] == ""

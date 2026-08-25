from app import feishu


class MockResponse:
    def __init__(self, code=0):
        self.code = code

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": self.code}


def test_feishu_disabled_without_webhook(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "")
    assert feishu.send_feishu("test") is False


def test_feishu_success(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *args, **kwargs: MockResponse(0),
    )
    assert feishu.send_feishu("test") is True


def test_feishu_business_error(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *args, **kwargs: MockResponse(999),
    )
    assert feishu.send_feishu("test") is False


def test_feishu_retry_after_network_error(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")

    calls = {"count": 0}

    def failed_post(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("network error")

    monkeypatch.setattr(feishu.requests, "post", failed_post)
    monkeypatch.setattr(feishu.time, "sleep", lambda *_: None)

    assert feishu.send_feishu("test") is False
    assert calls["count"] == feishu.MAX_RETRIES

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
    assert feishu.send_feishu("测试") is False


def test_feishu_success(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    captured = {}

    def post(*args, **kwargs):
        captured["payload"] = kwargs.get("json")
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    assert feishu.send_feishu("精简日报正文") is True
    payload = captured["payload"]
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "AI 新项目雷达"
    assert payload["card"]["elements"][0]["text"]["content"] == "精简日报正文"


def test_feishu_business_error(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *args, **kwargs: MockResponse(999),
    )
    monkeypatch.setattr(feishu.time, "sleep", lambda *_: None)
    assert feishu.send_feishu("测试") is False


def test_feishu_retry_after_network_error(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")

    calls = {"count": 0}

    def failed_post(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("网络错误")

    monkeypatch.setattr(feishu.requests, "post", failed_post)
    monkeypatch.setattr(feishu.time, "sleep", lambda *_: None)

    assert feishu.send_feishu("测试") is False
    assert calls["count"] == feishu.MAX_RETRIES

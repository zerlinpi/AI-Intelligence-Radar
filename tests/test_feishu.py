from app import feishu
from app.cards.models import CardEnvelope


class MockResponse:
    def __init__(self, code=0, status_code=200):
        self.code = code
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": self.code}


def test_feishu_disabled_without_webhook(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "")
    assert feishu.send_feishu("测试") is False
    assert feishu.send_feishu_cards([]) is False


def test_legacy_feishu_success(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    captured = {}

    def post(*args, **kwargs):
        captured["payload"] = kwargs.get("json")
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    assert feishu.send_feishu("精简日报正文") is True
    payload = captured["payload"]
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["template"] == "turquoise"


def test_structured_cards_are_sent_in_order(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    cards = [
        CardEnvelope(
            card_type=name,
            payload={
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"content": name}},
                    "elements": [],
                },
            },
            fallback_text=f"{name} fallback",
        )
        for name in ("summary", "compliance", "products")
    ]

    assert feishu.send_feishu_cards(cards) is True
    assert [item["card"]["header"]["title"]["content"] for item in sent] == [
        "summary",
        "compliance",
        "products",
    ]


def test_payload_over_budget_uses_plain_text_fallback(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(feishu, "FEISHU_MAX_PAYLOAD_BYTES", 100)
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    card = CardEnvelope(
        card_type="products",
        payload={
            "msg_type": "interactive",
            "card": {"elements": [{"text": "A" * 500}]},
        },
        fallback_text="产品机会纯文本",
    )

    assert feishu.send_feishu_cards([card]) is True
    assert len(sent) == 1
    assert sent[0]["msg_type"] == "text"
    assert "产品机会纯文本" in sent[0]["content"]["text"]


def test_card_failure_falls_back_to_plain_text(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    sent = []

    def post(*args, **kwargs):
        payload = kwargs["json"]
        sent.append(payload)
        if payload["msg_type"] == "interactive":
            return MockResponse(code=999)
        return MockResponse(code=0)

    monkeypatch.setattr(feishu.requests, "post", post)

    card = CardEnvelope(
        card_type="summary",
        payload={
            "msg_type": "interactive",
            "card": {"elements": []},
        },
        fallback_text="摘要降级",
    )

    assert feishu.send_feishu_cards([card]) is True
    assert [payload["msg_type"] for payload in sent] == ["interactive", "text"]


def test_429_retries(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(feishu, "FEISHU_MAX_RETRIES", 3)
    monkeypatch.setattr(feishu, "_retry_sleep", lambda *_: None)
    calls = {"count": 0}

    def post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            return MockResponse(status_code=429)
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    assert feishu.send_feishu("测试") is True
    assert calls["count"] == 3


def test_400_does_not_retry(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    calls = {"count": 0}

    def post(*args, **kwargs):
        calls["count"] += 1
        return MockResponse(status_code=400)

    monkeypatch.setattr(feishu.requests, "post", post)

    assert feishu.send_feishu("测试") is False
    assert calls["count"] == 1

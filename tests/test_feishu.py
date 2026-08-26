from app import feishu
from app.cards.models import CardEnvelope
from app.core import outbox


class MockResponse:
    def __init__(self, code=0, status_code=200):
        self.code = code
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": self.code}


def _cards():
    return [
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


def test_feishu_disabled_without_webhook(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "")
    assert feishu.send_feishu("测试") is False
    assert feishu.send_feishu_cards([], durable=False) is False


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

    assert feishu.send_feishu_cards(_cards(), durable=False) is True
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

    assert feishu.send_feishu_cards([card], durable=False) is True
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

    assert feishu.send_feishu_cards([card], durable=False) is True
    assert [payload["msg_type"] for payload in sent] == ["interactive", "text"]


def test_invalid_json_value_uses_plain_text_fallback(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    sent = []
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *args, **kwargs: sent.append(kwargs["json"]) or MockResponse(0),
    )

    card = CardEnvelope(
        card_type="summary",
        payload={"msg_type": "interactive", "bad": float("nan")},
        fallback_text="严格JSON降级",
    )
    assert feishu.send_feishu_cards([card], durable=False) is True
    assert sent[0]["msg_type"] == "text"


def test_durable_outbox_resumes_only_unsent_cards(monkeypatch, tmp_path):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(feishu, "FEISHU_MAX_RETRIES", 1)
    monkeypatch.setattr(outbox, "FEISHU_OUTBOX_DIR", str(tmp_path))

    sent_titles = []
    phase = {"fail": True}

    def post(*args, **kwargs):
        payload = kwargs["json"]
        if payload["msg_type"] == "interactive":
            title = payload["card"]["header"]["title"]["content"]
            sent_titles.append(title)
            if title == "compliance" and phase["fail"]:
                return MockResponse(status_code=500)
        elif phase["fail"]:
            return MockResponse(status_code=500)
        return MockResponse(0)

    monkeypatch.setattr(feishu.requests, "post", post)

    assert feishu.send_feishu_cards(_cards(), run_id="run-1", durable=True) is False
    assert (tmp_path / "run-1.json").exists()
    assert sent_titles[0] == "summary"

    phase["fail"] = False
    sent_titles.clear()
    assert feishu.flush_feishu_outbox() is True
    assert sent_titles == ["compliance", "products"]
    assert not (tmp_path / "run-1.json").exists()


def test_corrupt_outbox_is_quarantined(monkeypatch, tmp_path):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK", "https://example.com")
    monkeypatch.setattr(outbox, "FEISHU_OUTBOX_DIR", str(tmp_path))
    bad = tmp_path / "bad-run.json"
    bad.write_text("not-json", encoding="utf-8")

    assert feishu.flush_feishu_outbox() is False
    assert not bad.exists()
    assert (tmp_path / "bad" / "bad-run.json").exists()


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

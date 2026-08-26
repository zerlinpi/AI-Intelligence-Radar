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
    assert payload["card"]["config"]["wide_screen_mode"] is True
    assert payload["card"]["header"]["template"] == "turquoise"
    assert payload["card"]["header"]["title"]["content"] == "美国跨境经营雷达"
    assert payload["card"]["elements"][0]["text"]["content"] == "精简日报正文"


def test_product_compliance_highlights_use_two_column_background_blocks():
    message = "\n".join(
        [
            "**C｜美国市场产品审核**",
            "> **审核简报：** 今日重点核对高风险产品准入资料。",
            "> 🎯 **影响产品：** **儿童产品、蓝牙设备**",
            "> ⚠️ **风险：** **可能导致清关延误或销售受阻**",
            "> 📋 **准备资料：** **测试报告、CPC/GCC、FCC授权资料**",
        ]
    )

    elements = feishu.build_card_elements(message)
    highlights = [item for item in elements if item.get("tag") == "column_set"]

    assert len(highlights) == 4
    assert all(item["background_style"] == "grey" for item in highlights)
    assert all(len(item["columns"]) == 2 for item in highlights)

    labels = [
        item["columns"][0]["elements"][0]["text"]["content"]
        for item in highlights
    ]
    bodies = [
        item["columns"][1]["elements"][0]["text"]["content"]
        for item in highlights
    ]

    assert any("审核简报" in label for label in labels)
    assert any("影响产品" in label for label in labels)
    assert any("风险" in label for label in labels)
    assert any("准备资料" in label for label in labels)
    assert any("儿童产品" in body for body in bodies)
    assert any("清关延误" in body for body in bodies)


def test_long_report_fields_are_compacted_without_losing_label():
    long_text = "A" * 220
    elements = feishu.build_card_elements(
        f"> ⚠️ **风险：** **{long_text}**\n**产品描述：** {long_text}"
    )

    highlight = next(item for item in elements if item.get("tag") == "column_set")
    label_text = highlight["columns"][0]["elements"][0]["text"]["content"]
    body_text = highlight["columns"][1]["elements"][0]["text"]["content"]
    normal_text = next(item for item in elements if item.get("tag") == "div")["text"]["content"]

    assert "风险" in label_text
    assert "…" in body_text
    assert "**产品描述：**" in normal_text
    assert "…" in normal_text
    assert len(body_text) <= feishu.DISPLAY_LIMITS["风险"] + 1


def test_compact_limits_cover_core_decision_fields():
    assert feishu.DISPLAY_LIMITS["影响产品"] <= 70
    assert feishu.DISPLAY_LIMITS["风险"] <= 80
    assert feishu.DISPLAY_LIMITS["准备资料"] <= 90
    assert feishu.DISPLAY_LIMITS["产品描述"] <= 110
    assert feishu.DISPLAY_LIMITS["价值判断"] <= 90


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

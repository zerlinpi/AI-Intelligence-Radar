from app.cards.models import ActionItem, ComplianceDecision, DailySummary, ReportDecisionModel
from app.report_copy import (
    project_display_description, safe_outbound_payload, safe_policy_display_text,
    safe_project_insight,
)


HF_CARD = "task: text-generation | library: transformers | MODEL_CARD: Introduction " + "A model readme with full code and CLI tutorials. " * 80
POLICY_RSS = "Official safety guidance for US consumer imports. " * 80
CHINESE_LONG = "这是完整且已核验的中文分析，不能因为文本很长而被自动丢弃。" * 200


def test_huggingface_model_card_and_mixed_chinese_preface_are_removed():
    text = project_display_description("已有项目说明：" + HF_CARD, source_name="Hugging Face")
    assert "MODEL_CARD:" not in text
    assert "中文功能摘要尚未完成核验" in text


def test_rss_english_or_html_policy_does_not_render_raw():
    assert "Official safety guidance" not in safe_policy_display_text(POLICY_RSS)
    assert "官方原文" in safe_policy_display_text(POLICY_RSS)
    assert "中文内容尚未完成核验" in safe_policy_display_text("<div>Official safety rule</div>")


def test_chinese_long_content_preserved_without_truncation():
    assert safe_policy_display_text(CHINESE_LONG) == CHINESE_LONG
    assert project_display_description(CHINESE_LONG) == CHINESE_LONG
    assert safe_project_insight(CHINESE_LONG) == CHINESE_LONG


def test_untrusted_project_insight_cannot_resurface_raw_documentation():
    assert "MODEL_CARD:" not in safe_project_insight("研究结论：" + HF_CARD)
    assert "中文摘要尚未完成核验" in safe_project_insight("研究结论：" + HF_CARD)


def test_cached_card_payload_and_split_readme_fragments_sanitized():
    cached = {
        "msg_type": "interactive",
        "card": {"header": {"title": {"content": "GitHub 核心项目"}}, "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "**Flickersoft/serval**"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**它能做什么**\nREADME: " + POLICY_RSS}},
            {"tag": "div", "text": {"tag": "lark_md", "content": POLICY_RSS}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "这是已核验的中文研究判断。"}},
        ]}
    }
    sanitized, changed = safe_outbound_payload(cached)
    assert changed
    lines = [e["text"]["content"] for e in sanitized["card"]["elements"]]
    assert "Flickersoft/serval" in lines[0]
    assert "README:" not in str(lines)
    assert "Official safety guidance" not in str(lines)
    assert "这是已核验的中文研究判断。" == lines[-1]
    assert "README:" in str(cached)


def test_live_report_policy_fields_are_safe_even_without_llm():
    policy = ComplianceDecision(
        focus="产品合规审核",
        title="CPSC Import guidance",
        source_name="CPSC",
        requirement=POLICY_RSS,
        impact="影响： " + POLICY_RSS,
        affected_products="中文说明： " + POLICY_RSS,
        risk="风险提示： " + POLICY_RSS,
        preparation=POLICY_RSS,
        action="Now read the official document.",
    )
    summary = DailySummary(date_text="10月08日", judgment="今日优先核对监管政策.", actions=[
        ActionItem("必须", "核对政策原文。")
    ])
    model = ReportDecisionModel(summary=summary, compliance=[policy], products=[])
    from app.cards.priority_builders import build_compliance_cards
    serialized = str(build_compliance_cards(model))
    assert "Official safety guidance" not in serialized
    assert "Now read the official document" not in serialized
    assert "政策中文内容尚未完成核验" in serialized


def test_feishu_sender_filters_cached_card_and_its_text_fallback(monkeypatch):
    from app import feishu
    from app.cards.models import CardEnvelope

    old = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "GitHub 核心项目"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "**项目名**\nFlickersoft/serval"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "**它能做什么**\n" + HF_CARD}},
            ],
        },
    }
    captured = []

    def fake_post(payload, card_type):
        captured.append((payload, card_type))
        return len(captured) == 2

    monkeypatch.setattr(feishu, "_post_payload", fake_post)
    card = CardEnvelope(
        card_type="products-github",
        payload=old,
        fallback_text="GitHub 核心项目\n" + HF_CARD,
    )
    assert feishu._send_envelope(card)
    assert len(captured) == 2
    assert captured[0][0]["msg_type"] == "interactive"
    assert captured[1][0]["msg_type"] == "text"
    assert "MODEL_CARD:" not in str(captured)
    assert "A model readme" not in str(captured)
    assert "中文摘要尚未完成核验" in str(captured)
    assert "MODEL_CARD:" in str(old)


def test_fallback_policy_prep_keeps_original_data_for_scoring():
    from scripts.prepare_local_fallback import _policy_analysis
    from app.models.radar_item import RadarItem

    item = RadarItem(
        title="US safety guidance",
        source="cpsc_compliance",
        category="policy",
        url="https://www.cpsc.gov/example",
        description=POLICY_RSS,
        metrics={"policy_score": 70},
    )
    result = _policy_analysis(item)
    assert "Official safety guidance" not in result["purpose"]
    assert "政策中文内容尚未完成核验" in result["purpose"]
    assert item.description == POLICY_RSS

from app.chatgpt_feed import report_model_from_dict
from app.cards import build_daily_cards


def sample_report():
    return {
        "date_text": "2026-09-09",
        "judgment": "美国合规侧关注新品审核变化；产品侧优先研究具备真实增长证据的 Agent 工具。",
        "actions": [
            {"label": "必须", "text": "核对高风险合规变化并确认受影响 SKU。"},
            {"label": "关注", "text": "跟踪 GitHub 高增速项目的真实工程活跃度。"},
            {"label": "研究", "text": "验证最值得产品化的 AI Agent 机会。"},
        ],
        "metrics": {"projects": 1, "policies": 1, "opportunities": 1},
        "compliance": [
            {
                "focus": "产品合规审核",
                "title": "FCC equipment authorization update",
                "source_name": "FCC",
                "authority": "FCC",
                "kind": "official",
                "age_text": "今日",
                "url": "https://www.fcc.gov/",
                "risk_level": "high",
                "impact_score": 91,
                "requirement": "确认适用设备授权路径。",
                "impact": "涉及无线射频产品的新品上架与进口准备。",
                "affected_products": "Bluetooth / Wi-Fi / RF 设备",
                "risk": "资料不完整可能影响上市节奏。",
                "preparation": "整理测试报告、认证编号和技术资料。",
                "action": "优先复核在售与待上新 SKU。",
            }
        ],
        "products": [
            {
                "title": "example/agent-project",
                "source_name": "GitHub",
                "age_text": "今日",
                "url": "https://github.com/example/agent-project",
                "trend_score": 94,
                "business_score": 90,
                "opportunity": "high",
                "tags": ["Agent", "Automation"],
                "description": "面向自动化工作流的 AI Agent 工具。",
                "growth_signal": "近期 Star 与工程提交同步增长。",
                "judgment": "具备明确产品化和内部提效价值。",
                "direction": "先验证跨境电商运营自动化场景。",
                "cross_border": True,
            }
        ],
    }


def test_chatgpt_feed_converts_to_existing_decision_model():
    model = report_model_from_dict(sample_report())

    assert model.summary.date_text == "2026-09-09"
    assert model.summary.actions[0].label == "必须"
    assert model.compliance[0].risk_level == "high"
    assert model.products[0].source_name == "GitHub"
    assert model.products[0].cross_border is True


def test_chatgpt_feed_uses_existing_feishu_card_builder():
    cards = build_daily_cards(report_model_from_dict(sample_report()))

    card_types = [card.card_type for card in cards]
    assert any(card_type.startswith("summary") for card_type in card_types)
    assert any(card_type.startswith("compliance") for card_type in card_types)
    assert any(card_type.startswith("products") for card_type in card_types)

    payloads = [card.payload for card in cards]
    assert all(payload.get("msg_type") == "interactive" for payload in payloads)
    assert any(payload["card"]["header"]["template"] == "red" for payload in payloads)
    assert any(payload["card"]["header"]["template"] == "blue" for payload in payloads)

from app.cards.builders import build_daily_cards
from app.cards.models import DailySummary, ProductDecision, ReportDecisionModel
from app.cards.text import payload_bytes
from app.config import FEISHU_MAX_PAYLOAD_BYTES


def _arxiv_model(description="研究内容"):
    long_title = (
        "Recursive Experiential-Working Memory for Long-Horizon AI Agents: "
        "A Unified Architecture for Persistent Task Reasoning and Skill Reuse"
    )
    product = ProductDecision(
        title=long_title,
        source_name="arXiv",
        age_text="15小时前",
        url="https://arxiv.org/abs/2608.12345",
        trend_score=36,
        business_score=70,
        opportunity="medium",
        tags=["AI Agent", "Memory", "可产品化", "长时任务"],
        description=description,
        growth_signal="最新发布研究",
        judgment="早期学术研究，无成熟产品；用户价值高，仍需真实业务环境验证。",
        direction="将递归记忆模块整合至电商客服或运营 Agent，提供长时任务自动化。",
        cross_border=False,
    )
    return ReportDecisionModel(
        summary=DailySummary(
            date_text="08月26日",
            judgment="今日研究信号值得关注。",
            metrics={"compliance": 0, "high_risk": 0, "projects": 1, "opportunities": 0},
        ),
        compliance=[],
        products=[product],
    )


def _serialized(cards):
    return "\n".join(str(card.payload) for card in cards)


def test_arxiv_uses_research_semantics_instead_of_growth_semantics():
    cards = build_daily_cards(_arxiv_model())
    product_cards = [card for card in cards if card.card_type.startswith("products")]
    serialized = _serialized(product_cards)

    assert "arXiv 研究论文" in serialized
    assert "产品化价值 70" in serialized
    assert "研究内容" in serialized
    assert "研究阶段" in serialized
    assert "产品化方向" in serialized
    assert "查看 arXiv 论文" in serialized
    assert "增长信号" not in serialized
    assert "🔥" not in serialized


def test_arxiv_full_title_and_all_tags_are_preserved():
    model = _arxiv_model()
    cards = build_daily_cards(model)
    serialized = _serialized(cards)

    assert model.products[0].title in serialized
    for tag in model.products[0].tags:
        assert tag in serialized


def test_very_long_arxiv_copy_is_paginated_without_truncation():
    long_description = (
        "BEGIN-ARXIV-研究内容。"
        + "该段用于验证飞书自动分页不会删除论文研究内容、实验说明和产品化上下文。" * 1200
        + "MID-ARXIV-研究内容。"
        + "继续保留后半段研究内容，任何超出单卡预算的文字只能拆卡不能裁掉。" * 1200
        + "END-ARXIV-研究内容。"
    )
    model = _arxiv_model(long_description)
    model.products[0].judgment = (
        "BEGIN-ARXIV-判断。" + "完整价值判断必须保留。" * 1200 + "END-ARXIV-判断。"
    )
    model.products[0].direction = (
        "BEGIN-ARXIV-方向。" + "完整产品化方向必须保留。" * 1200 + "END-ARXIV-方向。"
    )

    cards = build_daily_cards(model)
    serialized = _serialized(cards)

    for marker in (
        "BEGIN-ARXIV-研究内容",
        "MID-ARXIV-研究内容",
        "END-ARXIV-研究内容",
        "BEGIN-ARXIV-判断",
        "END-ARXIV-判断",
        "BEGIN-ARXIV-方向",
        "END-ARXIV-方向",
    ):
        assert marker in serialized

    product_cards = [card for card in cards if card.card_type.startswith("products")]
    assert len(product_cards) > 1
    for card in product_cards:
        assert payload_bytes(card.payload) <= FEISHU_MAX_PAYLOAD_BYTES

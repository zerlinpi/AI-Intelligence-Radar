from app.cards import build_daily_cards
from app.cards.models import DailySummary, ReportDecisionModel
from app.source_coverage import (
    coverage_snapshot,
    record_collector_health,
    reset_collection_health,
)


PROJECT_SOURCES = ("github", "hackernews", "huggingface", "arxiv", "producthunt")


def _record_complete_project_sources(*, failed=()):
    for source in PROJECT_SOURCES:
        record_collector_health(
            source,
            {
                "source": source,
                "success": source not in set(failed),
                "result_count": 0,
            },
        )


def _record_policy(*, failed_authorities=None, degraded_authorities=None, success=True):
    failed_authorities = list(failed_authorities or [])
    degraded_authorities = list(degraded_authorities or [])
    record_collector_health(
        "policy",
        {
            "source": "policy",
            "success": success,
            "result_count": 0,
            "policy_sources": {
                "complete": not failed_authorities,
                "query_complete": not failed_authorities and not degraded_authorities,
                "failed_authorities": failed_authorities,
                "degraded_authorities": degraded_authorities,
            },
        },
    )


def _empty_model():
    return ReportDecisionModel(
        summary=DailySummary(
            date_text="08月27日",
            judgment="今日未发现新增高风险合规事项。产品侧暂无达到最终价值门槛的新机会。",
            actions=[],
            metrics={
                "compliance": 0,
                "high_risk": 0,
                "projects": 0,
                "opportunities": 0,
            },
        ),
        compliance=[],
        products=[],
    )


def test_empty_success_is_not_treated_as_source_failure():
    reset_collection_health()
    _record_complete_project_sources()
    _record_policy()

    coverage = coverage_snapshot()

    assert coverage["available"] is True
    assert coverage["complete"] is True
    assert coverage["note"] == ""
    reset_collection_health()


def test_policy_authority_degradation_is_reported_as_incomplete_coverage():
    reset_collection_health()
    _record_complete_project_sources()
    _record_policy(degraded_authorities=["CPSC"])

    coverage = coverage_snapshot()

    assert coverage["available"] is True
    assert coverage["complete"] is False
    assert coverage["policy_complete"] is False
    assert "CPSC" in coverage["note"]
    assert "不能把缺失数据解释为“没有变化”" in coverage["note"]
    reset_collection_health()


def test_feishu_does_not_claim_no_compliance_change_when_policy_coverage_failed():
    reset_collection_health()
    _record_complete_project_sources()
    _record_policy(failed_authorities=["CPSC", "FCC"])

    cards = build_daily_cards(_empty_model())
    rendered = "\n".join(str(card.payload) for card in cards)

    assert "数据覆盖不完整" in rendered
    assert "当前不能据此判断“今日无新增合规变化”" in rendered
    assert "今日未发现新增的高影响 Amazon 政策、美国进口新规或产品审核要求。" not in rendered
    reset_collection_health()


def test_feishu_does_not_claim_no_product_opportunity_when_project_source_failed():
    reset_collection_health()
    _record_complete_project_sources(failed={"huggingface"})
    _record_policy()

    cards = build_daily_cards(_empty_model())
    rendered = "\n".join(str(card.payload) for card in cards)

    assert "Hugging Face" in rendered
    assert "本轮项目数据源覆盖不完整" in rendered
    assert "不能把缺失来源解释为“没有机会”" in rendered
    reset_collection_health()

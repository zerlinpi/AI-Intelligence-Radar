from datetime import datetime, timezone

from app.models.radar_item import RadarItem
from app.pipeline import apply_final_project_gate


def _project(
    title,
    *,
    source="github",
    business_score=85,
    opportunity="high",
    selection_score=70,
    trend_score=60,
    action="先做一个最小原型并用真实业务数据验证核心效果。",
    summary="该项目能直接改善现有业务或产品开发流程，但仍需要真实数据验证投入产出。",
    purpose="这是一个具备明确工作机制和目标使用场景的可复用项目。",
    priority_tags=None,
    physical_product_path=False,
):
    item = RadarItem(
        title=title,
        source=source,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        description="Enough source material to support a reliable product decision.",
        created_at=datetime.now(timezone.utc),
        metrics={
            "selection_score": selection_score,
            "priority_score": selection_score,
            "priority_tags": priority_tags or ["跨境电商", "可产品化"],
            "physical_product_path": physical_product_path,
        },
    )
    item.trend_score = trend_score
    item.analysis = {
        "business_score": business_score,
        "opportunity": opportunity,
        "purpose": purpose,
        "summary": summary,
        "startup_ideas": [action] if action else [],
        "llm_meta": {"success": True, "fallback": False},
    }
    return item


def test_high_score_project_without_action_is_not_pushed():
    item = _project("Actionless Seller Tool", business_score=95, action="")
    result = apply_final_project_gate([item])
    assert result == []
    assert item.metrics["final_report_eligible"] is False
    assert "可执行" in item.metrics["final_gate_reason"]


def test_huggingface_high_score_without_cross_border_or_physical_product_path_is_rejected():
    item = _project(
        "Generic Edge Model",
        source="huggingface",
        business_score=96,
        priority_tags=["技术前沿", "硬件开发", "可产品化"],
        physical_product_path=False,
    )
    result = apply_final_project_gate([item])
    assert result == []
    assert "实体商品落地路径" in item.metrics["final_gate_reason"]


def test_huggingface_model_with_real_physical_product_path_can_pass():
    item = _project(
        "Security Camera Edge Model",
        source="huggingface",
        business_score=88,
        priority_tags=["技术前沿", "硬件开发", "实体商品机会", "商品·安防", "可产品化"],
        physical_product_path=True,
    )
    result = apply_final_project_gate([item])
    assert result == [item]
    assert item.metrics["final_report_eligible"] is True
    assert item.metrics["final_actionable"] is True
    assert item.metrics["final_utility_score"] > 0


def test_final_projects_are_resorted_by_business_and_execution_utility():
    lower = _project(
        "Useful But Lower",
        business_score=72,
        selection_score=66,
        trend_score=90,
    )
    stronger = _project(
        "Stronger Product Opportunity",
        business_score=94,
        selection_score=86,
        trend_score=55,
    )

    result = apply_final_project_gate([lower, stronger])
    assert [item.title for item in result] == [
        "Stronger Product Opportunity",
        "Useful But Lower",
    ]
    assert stronger.metrics["final_utility_score"] > lower.metrics["final_utility_score"]

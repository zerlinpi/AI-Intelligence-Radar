from datetime import datetime, timezone

from app.cards.builders import _project_elements
from app.cards.models import ProductDecision
from app.models.radar_item import RadarItem
from app.pipeline import _to_product_decision
from app.report_copy import project_display_description
from scripts.prepare_local_fallback import _project_analysis


LONG_README = (
    "Self-hosted NVR with on-device AI."
    " | topics: rtsp onnx nvr computer-vision"
    " | language: C# | README: Quickstart "
    + "Detailed setup instructions and technical components. " * 180
)


def test_raw_readme_never_enters_report_copy():
    text = project_display_description(
        LONG_README, tags=["硬件开发", "实体商品机会"], source_name="GitHub"
    )
    assert "README:" not in text
    assert "Quickstart" not in text
    assert "topics:" not in text
    assert "已识别方向：硬件开发、实体商品机会" in text
    assert "中文功能摘要尚未完成核验" in text
    assert len(text) < 150


def test_untranslated_short_english_is_not_misrepresented_as_chinese_summary():
    description = project_display_description(
        "A self-hosted agent workflow and observability toolkit.",
        source_name="GitHub",
    )
    assert "agent workflow" not in description
    assert "GitHub 仓库" in description


def test_existing_real_chinese_analysis_is_kept_verbatim():
    original = "该框架支持端侧视觉分析和本地视频处理，部署前还需验证设备兼容性。"
    assert project_display_description(original, source_name="GitHub") == original


def test_pipeline_product_decision_filters_fallback_raw_english_readme():
    item = RadarItem(
        title="Flickersoft/serval",
        source="github",
        url="https://github.com/Flickersoft/serval",
        description=LONG_README,
        trend_score=40,
        created_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        metrics={"priority_tags": ["技术前沿", "硬件开发"], "stars": 11},
    )
    item.analysis = {
        "purpose": "项目原始说明：" + LONG_README,
        "summary": "请验证真实工程证据。",
        "startup_ideas": ["检查部署配置。"],
        "business_score": 60,
    }
    decision = _to_product_decision(item)
    assert "README:" not in decision.description
    assert "中文功能摘要尚未完成核验" in decision.description
    assert decision.judgment == "请验证真实工程证据。"
    assert item.description == LONG_README


def test_pre_generated_local_fallback_never_copies_readme_into_purpose():
    item = RadarItem(
        title="Flickersoft/serval",
        source="github",
        url="https://github.com/Flickersoft/serval",
        description=LONG_README,
        metrics={"priority_tags": ["硬件开发"], "selection_score": 63},
    )
    result = _project_analysis(item)
    assert "README:" not in result["purpose"]
    assert "中文功能摘要尚未完成核验" in result["purpose"]
    assert result["llm_meta"]["fallback"] is True


def test_feishu_card_guard_also_cleans_external_feed_project():
    project = ProductDecision(
        title="Flickersoft/serval",
        source_name="GitHub",
        age_text="2天前",
        url="https://github.com/Flickersoft/serval",
        tags=["硬件开发"],
        description=LONG_README,
        judgment="先核验工程进度。",
        direction="检查原始仓库。",
    )
    elements = _project_elements(project, 1)
    rendered = str(elements)
    assert "README:" not in rendered
    assert "Detailed setup instructions" not in rendered
    assert "中文功能摘要尚未完成核验" in rendered
    assert "先核验工程进度" in rendered

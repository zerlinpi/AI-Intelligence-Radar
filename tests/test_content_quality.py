from app.ai import analyzer
from app.content_quality import copy_similarity, distinct_sentences, is_redundant_copy


def test_copy_similarity_detects_same_meaning_with_small_format_changes():
    left = "该工具自动生成 Amazon Listing，并支持多语言本地化。"
    right = "该工具自动生成Amazon Listing，并支持多语言本地化。"
    assert copy_similarity(left, right) > 0.9
    assert is_redundant_copy(right, [left]) is True


def test_distinct_sentences_keeps_new_information_only():
    purpose = "该工具自动生成 Amazon Listing，并支持多语言本地化。"
    judgment = (
        "该工具自动生成 Amazon Listing，并支持多语言本地化。"
        "真正价值在于可减少多站点人工改写，但转化率提升仍需 A/B 测试。"
    )
    cleaned = distinct_sentences(judgment, [purpose])
    assert "自动生成 Amazon Listing" not in cleaned
    assert "A/B 测试" in cleaned


def test_analyzer_postprocess_removes_repeated_project_direction():
    item = {
        "title": "Seller Listing Tool",
        "description": "Amazon listing automation",
        "source": "github",
        "trend_score": 70,
        "metrics": {"eligibility_reason": "可直接用于跨境电商业务"},
    }
    raw = {
        "结果": [[
            1,
            "为 Amazon 卖家自动生成 Listing，并完成多语言本地化。",
            "可减少多站点人工改写，但效果仍需通过真实 Listing 的 A/B 测试验证。",
            85,
            "高",
            "为 Amazon 卖家自动生成 Listing，并完成多语言本地化。",
            "",
            "",
            "",
        ]]
    }
    result = analyzer._normalize_batch_result(raw, [item], {"success": True})[0]
    assert result["startup_ideas"] == []
    assert "A/B 测试" in result["summary"]


def test_analyzer_prompt_requires_non_overlapping_field_roles():
    prompt = analyzer._build_prompt("[]")
    assert "去重复写作协议" in prompt
    assert "禁止把同一句事实换同义词重复到相邻字段" in prompt
    assert "若某字段没有新增信息，允许返回空字符串" in prompt
    assert "热度高、发布时间近只能作为排序信号" in prompt
    assert "资=本地资格判断理由" in prompt

from app.ai.analyzer import _fallback_result


def test_llm_fallback_result():
    result = _fallback_result({"description": "demo"})

    assert result["trend_score"] == 50
    assert result["business_score"] == 50
    assert result["opportunity"] == "medium"
    assert "startup_ideas" in result

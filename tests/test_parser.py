from app.ai.parser import parse_json_response


def test_parse_markdown_json_response():
    content = """```json
    {"summary":"AI project","business_score":80}
    ```"""

    result = parse_json_response(content)

    assert result["summary"] == "AI project"
    assert result["business_score"] == 80
    assert isinstance(result["startup_ideas"], list)


def test_parse_invalid_response_returns_default_structure():
    result = parse_json_response("not json")

    assert "summary" in result
    assert "trend_score" in result
    assert "business_score" in result
    assert isinstance(result["startup_ideas"], list)


def test_parse_non_dict_response_returns_default_structure():
    result = parse_json_response("[]")

    assert isinstance(result, dict)
    assert result["opportunity"] == "medium"

from app.ai.parser import parse_json_response


def test_llm_json_parser():
    result = parse_json_response('```json\n{"summary":"ok"}\n```')
    assert result["summary"] == "ok"


def test_llm_json_parser_plain_json():
    result = parse_json_response('{"score": 90}')
    assert result["score"] == 90

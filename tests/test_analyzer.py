from app.ai import analyzer


class FakeUsage:
    prompt_tokens = 120
    completion_tokens = 80
    total_tokens = 200


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]
        self.usage = FakeUsage()


class FakeClient:
    calls = []

    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                FakeClient.calls.append(kwargs)
                return FakeResponse(
                    '{"结果":['
                    '{"序号":1,"摘要":"正在快速增长","商业分":90,"机会":"高","建议":"关注开发者工具"},'
                    '{"序号":2,"摘要":"早期需求明显","商业分":75,"机会":"中","建议":"观察付费转化"}'
                    ']}'
                )


def test_analyzer_fallback_without_key(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")

    result = analyzer.analyze_item(
        {"description": "demo", "trend_score": 80}
    )

    assert result["llm_meta"]["fallback"] is True
    assert "缺少" in result["llm_meta"]["reason"]


def test_analyzer_success(monkeypatch):
    FakeClient.calls.clear()
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        analyzer,
        "call_llm_with_retry",
        lambda func: (
            func(),
            {
                "success": True,
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ),
    )

    result = analyzer.analyze_item(
        {
            "title": "AI Agent",
            "description": "test project",
            "metrics": {"stars": 100},
            "trend_score": 70,
        }
    )

    assert result["summary"] == "正在快速增长"
    assert result["business_score"] == 90
    assert result["opportunity"] == "high"
    assert result["startup_ideas"] == ["关注开发者工具"]


def test_batch_analyzer_uses_one_request_for_multiple_items(monkeypatch):
    FakeClient.calls.clear()
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        analyzer,
        "call_llm_with_retry",
        lambda func: (func(), {"success": True, "usage": {}}),
    )

    results = analyzer.analyze_items(
        [
            {
                "title": "项目一",
                "description": "A" * 1000,
                "metrics": {"stars": 100, "unused": "x" * 1000},
                "trend_score": 80,
            },
            {
                "title": "项目二",
                "description": "第二个项目",
                "metrics": {"upvotes": 50},
                "trend_score": 70,
            },
        ]
    )

    assert len(results) == 2
    assert len(FakeClient.calls) == 1

    prompt = FakeClient.calls[0]["messages"][0]["content"]
    assert "A" * 241 not in prompt
    assert "unused" not in prompt
    assert FakeClient.calls[0]["max_tokens"] == min(
        analyzer.LLM_MAX_TOKENS,
        analyzer.MAX_OUTPUT_TOKENS,
    )


def test_batch_analyzer_caps_old_environment_token_value(monkeypatch):
    FakeClient.calls.clear()
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "LLM_MAX_TOKENS", 1200)
    monkeypatch.setattr(analyzer, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        analyzer,
        "call_llm_with_retry",
        lambda func: (func(), {"success": True, "usage": {}}),
    )

    analyzer.analyze_items(
        [
            {
                "title": "项目一",
                "description": "测试",
                "metrics": {"stars": 10},
                "trend_score": 80,
            }
        ]
    )

    assert FakeClient.calls[0]["max_tokens"] == 700

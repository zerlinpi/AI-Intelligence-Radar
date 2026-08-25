from app.ai import analyzer


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return FakeResponse(
                    '{"summary":"ok","business_score":90,"startup_ideas":[]}'
                )


def test_analyzer_fallback_without_key(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")

    result = analyzer.analyze_item(
        {"description": "demo", "trend_score": 80}
    )

    assert result["llm_meta"]["fallback"] is True


def test_analyzer_success(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        analyzer,
        "call_llm_with_retry",
        lambda func: (func(), {"success": True}),
    )

    result = analyzer.analyze_item(
        {
            "title": "AI Agent",
            "description": "test project",
            "metrics": {"stars": 100},
            "trend_score": 70,
        }
    )

    assert result["summary"] == "ok"
    assert result["business_score"] == 90

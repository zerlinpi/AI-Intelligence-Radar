from app.ai import analyzer


class FakeUsage:
    prompt_tokens = 160
    completion_tokens = 100
    total_tokens = 260


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
                    '[1,"8月24日起调整卖家配送费模板","自配送卖家需检查现有模板",92,"高","立即核对配送模板"],'
                    '[2,"帮卖家自动生成商品Listing","跨境卖家场景明确且易做成SaaS",90,"高","做Listing优化工具"]'
                    ']}'
                )


def _mock_success(monkeypatch):
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
                    "prompt_tokens": 160,
                    "completion_tokens": 100,
                    "total_tokens": 260,
                },
            },
        ),
    )


def test_analyzer_fallback_without_key(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")

    result = analyzer.analyze_item(
        {"description": "demo", "trend_score": 80}
    )

    assert result["llm_meta"]["fallback"] is True
    assert "缺少" in result["llm_meta"]["reason"]
    assert result["purpose"]


def test_policy_fallback_uses_policy_language(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")

    result = analyzer.analyze_item(
        {"category": "policy", "description": "policy update"}
    )

    assert "政策" in result["purpose"]
    assert result["startup_ideas"]


def test_analyzer_success(monkeypatch):
    _mock_success(monkeypatch)

    result = analyzer.analyze_item(
        {
            "title": "Amazon shipping update",
            "description": "New seller shipping requirement",
            "category": "policy",
            "source": "amazon_policy",
        }
    )

    assert result["purpose"] == "8月24日起调整卖家配送费模板"
    assert result["summary"] == "自配送卖家需检查现有模板"
    assert result["business_score"] == 92
    assert result["opportunity"] == "high"
    assert result["startup_ideas"] == ["立即核对配送模板"]
    assert result["trend_score"] == 0


def test_batch_analyzer_uses_one_request_for_policy_and_project(monkeypatch):
    _mock_success(monkeypatch)

    results = analyzer.analyze_items(
        [
            {
                "title": "Amazon shipping update",
                "description": "A" * 1000,
                "category": "policy",
                "source": "amazon_policy",
                "metrics": {"policy_score": 88, "unused": "x" * 1000},
            },
            {
                "title": "项目二",
                "description": "第二个项目",
                "source": "github",
                "metrics": {"stars": 50, "priority_tags": ["跨境电商", "可产品化"]},
                "trend_score": 70,
            },
        ]
    )

    assert len(results) == 2
    assert len(FakeClient.calls) == 1

    prompt = FakeClient.calls[0]["messages"][0]["content"]
    assert "A" * 221 not in prompt
    assert "unused" not in prompt
    assert "类型(政/项)" in prompt
    assert "Amazon" in prompt
    assert "跨境电商" in prompt
    assert FakeClient.calls[0]["max_tokens"] == min(
        analyzer.LLM_MAX_TOKENS,
        analyzer.MAX_OUTPUT_TOKENS,
    )


def test_batch_analyzer_caps_old_environment_token_value(monkeypatch):
    _mock_success(monkeypatch)
    monkeypatch.setattr(analyzer, "LLM_MAX_TOKENS", 1200)

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

    assert FakeClient.calls[0]["max_tokens"] == 900

from app.ai import analyzer


class FakeUsage:
    prompt_tokens = 160
    completion_tokens = 100
    total_tokens = 260


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [FakeChoice(content, finish_reason)]
        self.usage = FakeUsage()


class FakeClient:
    calls = []
    responses = []

    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                FakeClient.calls.append(kwargs)
                if FakeClient.responses:
                    return FakeClient.responses.pop(0)
                return FakeResponse(
                    '{"结果":['
                    '[1,"受监管消费品进口时需电子申报合规证书","进口商需确认适用范围和申报义务",94,"高","核对CPC或GCC并准备eFiling数据","儿童产品及其他需CPC或GCC的受监管消费品","证书或申报数据不完整可能导致清关延误、整改或销售受阻","准备第三方测试报告、CPC或GCC及eFiling所需字段"],'
                    '[2,"面向Amazon卖家的Listing运营工具，自动生成标题、卖点并做本地化优化","卖家场景明确，既有增长信号又可直接做成订阅SaaS",90,"高","做多站点Listing优化工具","","",""]'
                    ']}'
                )


def _mock_success(monkeypatch):
    FakeClient.calls.clear()
    FakeClient.responses.clear()
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(analyzer, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        analyzer,
        "call_llm_with_retry",
        lambda func, **kwargs: (
            func(),
            {
                "success": True,
                "usage": {
                    "prompt_tokens": 160,
                    "completion_tokens": 100,
                    "reasoning_tokens": 60,
                    "total_tokens": 260,
                },
            },
        ),
    )


def test_analyzer_fallback_without_key_uses_original_description(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")
    result = analyzer.analyze_item(
        {
            "title": "Demo",
            "description": "AI tool for Amazon sellers",
            "trend_score": 80,
        }
    )
    assert result["llm_meta"]["fallback"] is True
    assert "缺少" in result["llm_meta"]["reason"]
    assert "AI tool for Amazon sellers" in result["purpose"]
    assert "暂无法生成" not in result["purpose"]


def test_policy_fallback_uses_original_policy_text(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")
    result = analyzer.analyze_item(
        {"category": "policy", "description": "CPSC certification update"}
    )
    assert "CPSC certification update" in result["purpose"]
    assert result["startup_ideas"]
    assert result["affected_products"]
    assert result["risk"]
    assert result["preparation"]


def test_fallback_does_not_hard_truncate_original_description(monkeypatch):
    monkeypatch.setattr(analyzer, "LLM_API_KEY", "")
    original = "BEGIN " + ("完整源数据 " * 800) + " END"
    result = analyzer.analyze_item({"title": "Demo", "description": original})
    assert "BEGIN" in result["purpose"]
    assert "END" in result["purpose"]


def test_analyzer_success(monkeypatch):
    _mock_success(monkeypatch)
    result = analyzer.analyze_item(
        {
            "title": "CPSC eFiling requirement",
            "description": "Importers must eFile certificates of compliance through CBP.",
            "category": "policy",
            "source": "cpsc_compliance",
            "metrics": {
                "policy_focus": "产品合规审核",
                "policy_authority": "CPSC",
                "policy_kind": "消费品安全",
            },
        }
    )
    assert "电子申报" in result["purpose"]
    assert result["business_score"] == 94
    assert result["opportunity"] == "high"
    assert result["startup_ideas"]
    assert result["trend_score"] == 0
    assert "儿童产品" in result["affected_products"]
    assert "清关延误" in result["risk"]
    assert "测试报告" in result["preparation"]


def test_batch_analyzer_uses_json_mode_max_thinking_and_four_value_paths(monkeypatch):
    _mock_success(monkeypatch)
    results = analyzer.analyze_items(
        [
            {
                "title": "CPSC eFiling requirement",
                "description": "A" * 1400,
                "category": "policy",
                "source": "cpsc_compliance",
                "metrics": {
                    "policy_score": 95,
                    "policy_focus": "产品合规审核",
                    "policy_authority": "CPSC",
                    "policy_kind": "消费品安全",
                    "unused": "x" * 1000,
                },
            },
            {
                "title": "ESP32 Edge AI Camera",
                "description": "Embedded on-device computer vision with BLE sensors",
                "source": "github",
                "metrics": {
                    "stars": 50,
                    "priority_tags": ["技术前沿", "硬件开发", "实体商品机会", "可产品化"],
                },
                "trend_score": 70,
            },
        ]
    )
    assert len(results) == 2
    assert len(FakeClient.calls) == 1
    call = FakeClient.calls[0]
    prompt = call["messages"][0]["content"]
    assert "A" * 1400 in prompt
    assert "unused" not in prompt
    assert "CPSC" in prompt
    assert "CPC/GCC/eFiling" in prompt
    assert "目标用户" in prompt
    assert "完整、准确、有决策价值优先" in prompt
    assert "跨境电商实用性" in prompt
    assert "技术前沿/工程创新" in prompt
    assert "硬件开发价值" in prompt
    assert "美国市场实体商品机会" in prompt
    assert "不得把猜测或营销措辞写成事实" in prompt
    assert "Hugging Face模型重点看" in prompt
    assert "arXiv重点看" in prompt
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "max"
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "temperature" not in call
    assert call["max_tokens"] == min(
        analyzer.LLM_MAX_TOKENS,
        analyzer.MAX_OUTPUT_TOKENS,
    )


def test_batch_analyzer_recovers_only_missing_rows(monkeypatch):
    _mock_success(monkeypatch)
    FakeClient.responses.extend(
        [
            FakeResponse(
                '{"结果":['
                '[1,"第一个项目用途完整","第一个项目判断完整",88,"高","第一个建议"]'
                ']}'
            ),
            FakeResponse(
                '{"结果":['
                '[2,"第二个项目用途已恢复","第二个项目判断已恢复",82,"高","第二个建议"]'
                ']}'
            ),
        ]
    )

    results = analyzer.analyze_items(
        [
            {"title": "项目一", "description": "描述一", "trend_score": 80},
            {"title": "项目二", "description": "描述二", "trend_score": 70},
        ]
    )

    assert len(FakeClient.calls) == 2
    assert results[0]["purpose"] == "第一个项目用途完整"
    assert results[1]["purpose"] == "第二个项目用途已恢复"
    assert not (results[1]["llm_meta"] or {}).get("fallback")

    retry_prompt = FakeClient.calls[1]["messages"][0]["content"]
    assert "项目二" in retry_prompt
    assert "项目一" not in retry_prompt


def test_batch_analyzer_allows_large_configured_output_budget(monkeypatch):
    _mock_success(monkeypatch)
    monkeypatch.setattr(analyzer, "LLM_MAX_TOKENS", 131072)
    analyzer.analyze_items(
        [{"title": "项目一", "description": "测试", "metrics": {"stars": 10}, "trend_score": 80}]
    )
    assert FakeClient.calls[0]["max_tokens"] == 131072


def test_batch_analyzer_caps_output_at_deepseek_model_limit(monkeypatch):
    _mock_success(monkeypatch)
    monkeypatch.setattr(analyzer, "LLM_MAX_TOKENS", 500000)
    analyzer.analyze_items(
        [{"title": "项目一", "description": "测试", "metrics": {"stars": 10}, "trend_score": 80}]
    )
    assert FakeClient.calls[0]["max_tokens"] == 384000

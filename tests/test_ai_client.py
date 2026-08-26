from types import SimpleNamespace

from app.ai import client


class ApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def test_llm_non_retryable_error_fails_fast(monkeypatch):
    calls = {"count": 0}

    def request():
        calls["count"] += 1
        raise ApiError("unauthorized", status_code=401)

    monkeypatch.setattr(client.time, "sleep", lambda *_: None)

    response, meta = client.call_llm_with_retry(request, retries=3)

    assert response is None
    assert meta["success"] is False
    assert meta["attempt"] == 1
    assert calls["count"] == 1


def test_llm_transient_error_retries(monkeypatch):
    calls = {"count": 0}

    class Response:
        usage = None

    def request():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ApiError("server error", status_code=500)
        return Response()

    monkeypatch.setattr(client.time, "sleep", lambda *_: None)

    response, meta = client.call_llm_with_retry(request, retries=2)

    assert response is not None
    assert meta["success"] is True
    assert meta["attempt"] == 2
    assert calls["count"] == 2


def test_collect_streamed_chat_completion_merges_reasoning_content_and_usage():
    usage = SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=80,
        total_tokens=200,
    )
    stream = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        reasoning_content="思考A",
                        content=None,
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        reasoning_content="思考B",
                        content='{"结果":',
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        reasoning_content=None,
                        content="[]}",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
        ),
        SimpleNamespace(choices=[], usage=usage),
    ]

    response = client.collect_streamed_chat_completion(stream)

    assert response.choices[0].message.reasoning_content == "思考A思考B"
    assert response.choices[0].message.content == '{"结果":[]}'
    assert response.choices[0].finish_reason == "stop"
    assert client.get_llm_model_usage(response) == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }


def test_deepseek_client_forces_streaming_and_collects(monkeypatch):
    calls = []

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(kwargs)
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                reasoning_content="分析中",
                                content=None,
                            ),
                            finish_reason=None,
                        )
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                reasoning_content=None,
                                content='{"结果":[]}',
                            ),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=10,
                        completion_tokens=5,
                        total_tokens=15,
                    ),
                ),
            ]

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(client, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(client, "LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr(client, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(client, "LLM_TIMEOUT_SECONDS", 900)

    wrapped = client.get_llm_client()
    response = wrapped.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "return json"}],
    )

    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert response.choices[0].message.content == '{"结果":[]}'
    assert response.choices[0].message.reasoning_content == "分析中"
    assert response.usage.total_tokens == 15

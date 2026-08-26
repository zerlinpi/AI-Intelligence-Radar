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

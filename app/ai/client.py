import time

from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}


def get_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client.

    Supports OpenAI, DeepSeek and any provider exposing an
    OpenAI-compatible API endpoint. Retries are handled by this project
    rather than by both the SDK and project code at the same time.
    """
    if not LLM_API_KEY:
        raise RuntimeError(
            "LLM API key is missing. Set LLM_API_KEY or OPENAI_API_KEY."
        )

    if not LLM_BASE_URL:
        raise RuntimeError(
            "LLM base URL is missing. Set LLM_BASE_URL."
        )

    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=45.0,
        max_retries=0,
    )


def get_llm_model() -> str:
    """Return configured LLM model name."""
    return LLM_MODEL


def get_llm_model_usage(response):
    """Extract token usage from OpenAI-compatible responses."""
    usage = getattr(response, "usage", None)

    if not usage:
        return {}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", 0),
    }


def _get_status_code(exc):
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code

    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _is_retryable(exc) -> bool:
    """Retry transient network/server/rate-limit failures only."""
    status_code = _get_status_code(exc)

    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False

    if status_code is None:
        return True

    return status_code == 408 or status_code == 429 or status_code >= 500


def call_llm_with_retry(request_func, retries=2, delay=2):
    """Execute an LLM request with bounded retry protection."""
    last_error = None
    attempts = 0

    for attempt in range(retries):
        attempts = attempt + 1

        try:
            start = time.time()
            response = request_func()

            return response, {
                "success": True,
                "latency": round(time.time() - start, 3),
                "attempt": attempts,
                "usage": get_llm_model_usage(response),
            }

        except Exception as exc:
            last_error = exc

            if not _is_retryable(exc):
                break

            if attempt < retries - 1:
                time.sleep(delay * attempts)

    return None, {
        "success": False,
        "error": str(last_error),
        "attempt": attempts,
        "usage": {},
    }

import time

from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def get_llm_client() -> OpenAI:
    """Create an OpenAI compatible client.

    Supports OpenAI, DeepSeek and any provider exposing an
    OpenAI-compatible API endpoint.
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
        timeout=60.0,
        max_retries=2,
    )


def get_llm_model() -> str:
    """Return configured LLM model name."""
    return LLM_MODEL


def get_llm_model_usage(response):
    """Extract token usage from OpenAI compatible responses."""
    usage = getattr(response, "usage", None)

    if not usage:
        return {}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", 0),
    }


def call_llm_with_retry(request_func, retries=3, delay=2):
    """Execute an LLM request with retry protection."""
    last_error = None

    for attempt in range(retries):
        try:
            start = time.time()
            response = request_func()

            return response, {
                "success": True,
                "latency": round(time.time() - start, 3),
                "attempt": attempt + 1,
                "usage": get_llm_model_usage(response),
            }

        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(delay)

    return None, {
        "success": False,
        "error": str(last_error),
        "attempt": retries,
        "usage": {},
    }

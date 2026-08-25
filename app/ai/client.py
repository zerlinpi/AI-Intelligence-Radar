import time
from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL


def get_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client.

    Supports OpenAI, DeepSeek and any provider exposing an
    OpenAI-compatible API endpoint.
    """
    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=60.0,
        max_retries=2,
    )


def call_llm_with_retry(request_func, retries=3, delay=2):
    """Execute an LLM request with lightweight retry protection."""
    last_error = None

    for attempt in range(retries):
        try:
            start = time.time()
            response = request_func()
            return response, {
                "success": True,
                "latency": round(time.time() - start, 3),
                "attempt": attempt + 1,
            }
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(delay)

    return None, {
        "success": False,
        "error": str(last_error),
        "attempt": retries,
    }

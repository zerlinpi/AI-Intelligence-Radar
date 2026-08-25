from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL


def get_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client.

    Supports OpenAI, DeepSeek and other providers exposing an
    OpenAI-compatible API endpoint.
    """
    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
    )

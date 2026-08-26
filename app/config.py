import os

from dotenv import load_dotenv


load_dotenv()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# OpenAI-compatible LLM configuration.
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    or "https://api.openai.com/v1"
).strip()
LLM_MODEL = (os.getenv("LLM_MODEL", "gpt-5.5-mini") or "gpt-5.5-mini").strip()
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)
LLM_MAX_TOKENS = max(_env_int("LLM_MAX_TOKENS", 1200), 1)

# Keep the default database path inside the Docker-persisted data directory.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/radar.db")

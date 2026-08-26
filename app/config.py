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

# 兼容 OpenAI 接口格式的模型配置，可用于 DeepSeek 等服务。
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    or "https://api.openai.com/v1"
).strip()
LLM_MODEL = (os.getenv("LLM_MODEL", "gpt-5.5-mini") or "gpt-5.5-mini").strip()
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)

# 一次批量分析最多包含 4 条政策和 10 个项目。
# DeepSeek thinking Token 与最终正文共用 completion 预算，因此默认预留 65536 Token。
# 这是输出上限，不是固定消耗；实际仍按模型真实生成量计费。
LLM_MAX_TOKENS = max(_env_int("LLM_MAX_TOKENS", 65536), 1)

# 日报属于离线分析任务，不追求秒级响应。默认允许单次模型请求思考 15 分钟，
# 避免 deepseek-v4-pro 在完整批量分析中因为短超时被误判为失败。
LLM_TIMEOUT_SECONDS = max(_env_float("LLM_TIMEOUT_SECONDS", 900), 30)

# 默认数据库位于 Docker 持久化目录中。
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/radar.db")

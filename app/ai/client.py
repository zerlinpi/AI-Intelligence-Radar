import time

from openai import OpenAI

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.core.logger import get_logger


logger = get_logger("模型客户端")

NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}

# DeepSeek 已于 2026-07-24 停止旧模型名。保留自动映射，避免服务器旧 .env
# 继续使用 deepseek-chat / deepseek-reasoner 时整批分析直接降级。
LEGACY_MODEL_ALIASES = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
}


def get_llm_client() -> OpenAI:
    """创建兼容 OpenAI 接口格式的模型客户端。

    日报是离线任务，允许模型长时间推理。SDK 自身不自动重试，
    由项目逻辑统一控制，避免出现不可控的重复请求。
    """
    if not LLM_API_KEY:
        raise RuntimeError(
            "缺少模型 API 密钥，请配置 LLM_API_KEY 或 OPENAI_API_KEY。"
        )

    if not LLM_BASE_URL:
        raise RuntimeError(
            "缺少模型接口地址，请配置 LLM_BASE_URL。"
        )

    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=float(LLM_TIMEOUT_SECONDS),
        max_retries=0,
    )


def get_llm_model() -> str:
    """返回当前有效模型名称，并兼容已经停用的 DeepSeek 旧别名。"""
    configured = str(LLM_MODEL or "").strip()
    resolved = LEGACY_MODEL_ALIASES.get(configured, configured)

    if resolved != configured:
        logger.warning(
            "检测到已停用模型名 %s，自动切换为 %s；请同步更新 .env",
            configured,
            resolved,
        )

    return resolved


def get_llm_model_usage(response):
    """读取兼容接口返回的 Token 使用量。"""
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
    """只重试网络、限流和服务端临时错误。"""
    status_code = _get_status_code(exc)

    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False

    if status_code is None:
        return True

    return status_code == 408 or status_code == 429 or status_code >= 500


def call_llm_with_retry(request_func, retries=2, delay=2):
    """以受控次数执行模型请求。"""
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

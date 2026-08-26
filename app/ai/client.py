import time
from types import SimpleNamespace

from openai import OpenAI

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
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


def _extra_attr(obj, name, default=None):
    """兼容旧版 OpenAI SDK 对服务商扩展字段的读取。"""
    value = getattr(obj, name, None)
    if value is not None:
        return value

    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict) and name in extra:
        return extra.get(name)

    return default


def collect_streamed_chat_completion(stream):
    """消费流式 Chat Completion，并还原为普通响应形态。

    DeepSeek thinking 模式会持续输出 reasoning_content。这里消费这些增量以维持
    长任务连接，但只把最终 content 交给日报 JSON 解析；思考内容不会写入数据库或飞书。
    """
    content_parts = []
    reasoning_parts = []
    usage = None
    finish_reason = ""
    chunk_count = 0
    first_chunk_logged = False

    for chunk in stream:
        chunk_count += 1

        if not first_chunk_logged:
            logger.info("DeepSeek 流式连接已建立，正在等待完整分析结果")
            first_chunk_logged = True

        chunk_usage = _extra_attr(chunk, "usage")
        if chunk_usage is not None:
            usage = chunk_usage

        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue

        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is not None:
            reasoning = _extra_attr(delta, "reasoning_content", "") or ""
            content = _extra_attr(delta, "content", "") or ""
            if reasoning:
                reasoning_parts.append(str(reasoning))
            if content:
                content_parts.append(str(content))

        current_finish = getattr(choice, "finish_reason", None)
        if current_finish:
            finish_reason = str(current_finish)

    if chunk_count == 0:
        raise RuntimeError("模型流式响应为空")

    final_content = "".join(content_parts)
    reasoning_content = "".join(reasoning_parts)

    logger.info(
        "模型流式响应完成：数据块=%s 思考字符=%s 正文字符=%s 结束原因=%s",
        chunk_count,
        len(reasoning_content),
        len(final_content),
        finish_reason or "未知",
    )

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=final_content,
                    reasoning_content=reasoning_content,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def get_llm_client():
    """创建兼容 OpenAI 接口格式的模型客户端。

    日报是离线任务，允许模型长时间推理。DeepSeek 默认转为流式接收，
    让 thinking 阶段持续有 SSE 数据经过连接，避免中间链路按约 90 秒空闲超时切断。
    对分析层仍返回普通 ChatCompletion 形态，因此不改变现有业务逻辑。
    """
    if not LLM_API_KEY:
        raise RuntimeError(
            "缺少模型 API 密钥，请配置 LLM_API_KEY 或 OPENAI_API_KEY。"
        )

    if not LLM_BASE_URL:
        raise RuntimeError(
            "缺少模型接口地址，请配置 LLM_BASE_URL。"
        )

    raw_client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=float(LLM_TIMEOUT_SECONDS),
        max_retries=0,
    )

    if str(LLM_PROVIDER or "").lower() != "deepseek":
        return raw_client

    def create_streamed_completion(**kwargs):
        # DeepSeek 官方支持 thinking + stream。把非流式长等待转换成 SSE，
        # 但最终仍聚合成一个普通响应交回 analyzer。
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
        stream = raw_client.chat.completions.create(**kwargs)
        return collect_streamed_chat_completion(stream)

    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_streamed_completion)
        )
    )


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

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

# 飞书自定义机器人官方请求体硬限制为 20 KB。项目默认使用 18 KiB 软预算，
# 同时硬性钳制在 20 KiB 以下，避免错误环境变量绕过发送前保护。
FEISHU_MAX_PAYLOAD_BYTES = min(
    max(_env_int("FEISHU_MAX_PAYLOAD_BYTES", 18 * 1024), 4096),
    20 * 1024,
)
FEISHU_PROJECTS_PER_CARD = min(
    max(_env_int("FEISHU_PROJECTS_PER_CARD", 5), 1),
    5,
)
FEISHU_MAX_RETRIES = min(max(_env_int("FEISHU_MAX_RETRIES", 3), 1), 5)
FEISHU_SEND_TIMEOUT_SECONDS = min(
    max(_env_float("FEISHU_SEND_TIMEOUT_SECONDS", 10), 3),
    60,
)
# 发送队列位于 Docker 持久化 data 目录；进程重启后可继续补发尚未成功的卡片。
FEISHU_OUTBOX_DIR = (
    os.getenv("FEISHU_OUTBOX_DIR", "./data/feishu-outbox")
    or "./data/feishu-outbox"
).strip()

REPORT_LOCALE = (os.getenv("REPORT_LOCALE", "zh-CN") or "zh-CN").strip()
REPORT_TIMEZONE = (
    os.getenv("REPORT_TIMEZONE", "Asia/Shanghai") or "Asia/Shanghai"
).strip()

# 兼容 OpenAI 接口格式的模型配置，可用于 DeepSeek 等服务。
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    or "https://api.openai.com/v1"
).strip()
LLM_MODEL = (os.getenv("LLM_MODEL", "gpt-5.5-mini") or "gpt-5.5-mini").strip()
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)

# DeepSeek V4 Pro 当前官方最大输出为 384K Token。日报默认使用 131072 Token，
# 给 4 条政策 + 10 个项目的 max thinking 批量分析留出更大余量；这是上限而非固定消耗。
# 同时把环境变量硬钳制在 384000，避免错误配置超过模型能力边界。
LLM_MAX_TOKENS = min(
    max(_env_int("LLM_MAX_TOKENS", 131072), 1),
    384000,
)

# 日报属于离线分析任务，不追求秒级响应。默认允许单次模型请求思考 15 分钟，
# 避免 deepseek-v4-pro 在完整批量分析中因为短超时被误判为失败。
LLM_TIMEOUT_SECONDS = max(_env_float("LLM_TIMEOUT_SECONDS", 900), 30)

# 默认数据库位于 Docker 持久化目录中。
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/radar.db")

# data 目录承担 SQLite、飞书 outbox、数据库备份和运行历史，磁盘空间过低时应在
# 调用 DeepSeek 前停止执行，避免数据库写到一半或 outbox 无法落盘。
DATA_MIN_FREE_MB = max(_env_int("DATA_MIN_FREE_MB", 256), 64)
DATABASE_BACKUP_DIR = (
    os.getenv("DATABASE_BACKUP_DIR", "./data/backups") or "./data/backups"
).strip()
DATABASE_BACKUP_RETENTION = min(
    max(_env_int("DATABASE_BACKUP_RETENTION", 7), 1),
    60,
)
RUN_HISTORY_FILE = (
    os.getenv("RUN_HISTORY_FILE", "./data/run-history.json")
    or "./data/run-history.json"
).strip()
RUN_HISTORY_LIMIT = min(max(_env_int("RUN_HISTORY_LIMIT", 100), 10), 1000)

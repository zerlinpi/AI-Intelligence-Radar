import os
from dataclasses import dataclass
from pathlib import Path
from typing import List
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from app.config import (
    DATABASE_URL,
    FEISHU_MAX_PAYLOAD_BYTES,
    FEISHU_OUTBOX_DIR,
    FEISHU_WEBHOOK,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    REPORT_TIMEZONE,
)
from app.database.session import engine


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str = ""
    required: bool = True


@dataclass(frozen=True)
class PreflightResult:
    checks: List[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks if check.required)

    @property
    def failures(self) -> List[str]:
        return [
            check.name
            for check in self.checks
            if check.required and not check.ok
        ]


def _valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _database_check() -> PreflightCheck:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if str(DATABASE_URL).startswith("sqlite:"):
                result = connection.execute(text("PRAGMA quick_check")).scalar()
                if str(result or "").lower() != "ok":
                    return PreflightCheck(
                        "数据库完整性",
                        False,
                        f"SQLite quick_check={result}",
                    )
        return PreflightCheck("数据库", True, "可连接且完整性检查通过")
    except Exception as exc:
        return PreflightCheck("数据库", False, str(exc))


def _database_path_check() -> PreflightCheck:
    if not str(DATABASE_URL).startswith("sqlite:///"):
        return PreflightCheck("数据库目录可写", True, "非文件型 SQLite")

    raw_path = str(DATABASE_URL)[len("sqlite:///"):]
    if not raw_path or raw_path == ":memory:":
        return PreflightCheck("数据库目录可写", True, "内存数据库")

    path = Path(raw_path).expanduser()
    parent = path.parent if str(path.parent) else Path(".")
    try:
        parent.mkdir(parents=True, exist_ok=True)
        writable = os.access(parent, os.W_OK)
        if path.exists():
            writable = writable and os.access(path, os.W_OK)
        return PreflightCheck(
            "数据库目录可写",
            bool(writable),
            str(parent.resolve()),
        )
    except Exception as exc:
        return PreflightCheck("数据库目录可写", False, str(exc))


def _directory_check(name: str, value: str) -> PreflightCheck:
    try:
        path = Path(str(value or "")).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        writable = os.access(path, os.W_OK)
        return PreflightCheck(name, bool(writable), str(path.resolve()))
    except Exception as exc:
        return PreflightCheck(name, False, str(exc))


def run_preflight() -> PreflightResult:
    checks: List[PreflightCheck] = []

    checks.append(_database_check())
    checks.append(_database_path_check())
    checks.append(_directory_check("飞书持久化队列目录", FEISHU_OUTBOX_DIR))

    checks.append(
        PreflightCheck(
            "飞书机器人地址",
            _valid_http_url(FEISHU_WEBHOOK),
            "已配置" if FEISHU_WEBHOOK else "未配置",
        )
    )
    checks.append(
        PreflightCheck(
            "模型密钥",
            bool(str(LLM_API_KEY or "").strip()),
            "已配置" if LLM_API_KEY else "未配置",
        )
    )
    checks.append(
        PreflightCheck(
            "模型接口地址",
            _valid_http_url(LLM_BASE_URL),
            str(LLM_BASE_URL or ""),
        )
    )
    checks.append(
        PreflightCheck(
            "模型名称",
            bool(str(LLM_MODEL or "").strip()),
            str(LLM_MODEL or ""),
        )
    )
    checks.append(
        PreflightCheck(
            "模型输出上限",
            int(LLM_MAX_TOKENS or 0) >= 8192,
            f"{LLM_MAX_TOKENS} Token",
        )
    )
    checks.append(
        PreflightCheck(
            "模型超时",
            float(LLM_TIMEOUT_SECONDS or 0) >= 120,
            f"{LLM_TIMEOUT_SECONDS} 秒",
        )
    )
    checks.append(
        PreflightCheck(
            "飞书 Payload 安全预算",
            4096 <= int(FEISHU_MAX_PAYLOAD_BYTES or 0) <= 20 * 1024,
            f"{FEISHU_MAX_PAYLOAD_BYTES} 字节",
        )
    )

    try:
        ZoneInfo(REPORT_TIMEZONE)
        timezone_ok = True
        timezone_detail = REPORT_TIMEZONE
    except ZoneInfoNotFoundError:
        timezone_ok = False
        timezone_detail = f"未知时区：{REPORT_TIMEZONE}"
    checks.append(PreflightCheck("日报时区", timezone_ok, timezone_detail))

    checks.extend(
        [
            PreflightCheck(
                "GitHub 访问令牌",
                bool(os.getenv("GITHUB_TOKEN")),
                "未配置时仍可运行，但限额较低",
                required=False,
            ),
            PreflightCheck(
                "Product Hunt 访问令牌",
                bool(os.getenv("PRODUCT_HUNT_TOKEN")),
                "未配置时自动跳过 Product Hunt",
                required=False,
            ),
        ]
    )

    return PreflightResult(checks=checks)

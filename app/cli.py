import os
import sys

from sqlalchemy import text

from app.config import (
    FEISHU_WEBHOOK,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
)
from app.database.session import engine
from app.pipeline import run_daily_radar


def _database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check():
    """只检查运行配置，不执行日报。"""
    required_checks = {
        "数据库": _database_available(),
        "飞书机器人地址": bool(FEISHU_WEBHOOK),
        "模型密钥": bool(LLM_API_KEY),
        "模型名称": bool(LLM_MODEL),
        "模型接口地址": bool(LLM_BASE_URL),
    }

    optional_checks = {
        "GitHub 访问令牌": bool(os.getenv("GITHUB_TOKEN")),
        "Product Hunt 访问令牌": bool(os.getenv("PRODUCT_HUNT_TOKEN")),
    }

    for name, status in required_checks.items():
        level = "正常" if status else "失败"
        print(f"[{level}] {name}")

    for name, status in optional_checks.items():
        level = "正常" if status else "提醒"
        print(f"[{level}] {name}")

    return all(required_checks.values())


def _print_run_summary(result):
    if not isinstance(result, dict):
        print("日报执行结束，但没有返回有效结果。")
        return

    if result.get("skipped"):
        print(f"日报已跳过：{result.get('reason') or '已有任务正在运行'}")
        return

    print(
        "日报执行完成："
        f"执行编号={result.get('execution_id', '-')} "
        f"项目数量={len(result.get('items', []))} "
        f"耗时={result.get('duration', 0)}秒"
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return 0 if check() else 1

    result = run_daily_radar()
    _print_run_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

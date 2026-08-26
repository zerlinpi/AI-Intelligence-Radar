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
    """Validate the runtime configuration without running the daily pipeline."""
    required_checks = {
        "Database": _database_available(),
        "Feishu Webhook": bool(FEISHU_WEBHOOK),
        "LLM API Key": bool(LLM_API_KEY),
        "LLM Model": bool(LLM_MODEL),
        "LLM Base URL": bool(LLM_BASE_URL),
    }

    optional_checks = {
        "GitHub Token": bool(os.getenv("GITHUB_TOKEN")),
        "Product Hunt Token": bool(os.getenv("PRODUCT_HUNT_TOKEN")),
    }

    for name, status in required_checks.items():
        level = "OK" if status else "FAIL"
        print(f"[{level}] {name}")

    for name, status in optional_checks.items():
        level = "OK" if status else "WARN"
        print(f"[{level}] {name}")

    return all(required_checks.values())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return 0 if check() else 1

    result = run_daily_radar()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

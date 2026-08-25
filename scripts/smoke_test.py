"""Production smoke test for AI Intelligence Radar.

Run after deployment:
    python scripts/smoke_test.py
"""

import os
import sys


def check_env():
    required = [
        "LLM_API_KEY",
        "FEISHU_WEBHOOK",
    ]

    missing = [key for key in required if not os.getenv(key)]

    if missing:
        print("Missing environment variables:")
        for key in missing:
            print(f"- {key}")
        return False

    print("Environment configuration OK")
    return True


def check_imports():
    try:
        from app.pipeline import run_daily_radar  # noqa: F401
        from app.ai.client import get_llm_client  # noqa: F401
        print("Application imports OK")
        return True
    except Exception as exc:
        print(f"Import check failed: {exc}")
        return False


if __name__ == "__main__":
    result = check_env() and check_imports()
    sys.exit(0 if result else 1)

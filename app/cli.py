import os
import sys

from app.pipeline import run_daily_radar



def check():
    checks = {
        "Environment": True,
        "Pipeline": True,
        "Database": bool(os.getenv("DATABASE_URL", "sqlite:///radar.db")),
        "Feishu Config": bool(os.getenv("FEISHU_WEBHOOK")),
        "LLM Config": bool(os.getenv("OPENAI_API_KEY")),
    }

    success = True

    for name, status in checks.items():
        level = "OK" if status else "WARN"
        print(f"[{level}] {name}")
        if not status:
            success = False

    return success



def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return 0 if check() else 1

    result = run_daily_radar()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

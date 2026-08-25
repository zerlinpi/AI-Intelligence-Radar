import os
import sys


def check(name, condition):
    status = "OK" if condition else "WARN"
    print(f"[{status}] {name}")
    return condition


def main():
    print("=" * 40)
    print("AI Intelligence Radar Verify")
    print("=" * 40)

    results = []
    results.append(check("Python Environment", sys.version_info >= (3, 10)))
    results.append(check("Database Config", bool(os.getenv("DATABASE_URL"))))
    results.append(check("LLM Config", bool(os.getenv("OPENAI_API_KEY"))))
    results.append(check("Feishu Config", bool(os.getenv("FEISHU_WEBHOOK"))))

    print("=" * 40)
    print("READY" if all(results) else "CHECK CONFIGURATION")


if __name__ == "__main__":
    main()

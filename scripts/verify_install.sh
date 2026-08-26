#!/usr/bin/env bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "== AI 情报雷达安装检查 =="

if ! command -v python >/dev/null 2>&1; then
  echo "缺少 Python，无法继续检查"
  exit 1
fi

python --version

if [ -f .env ]; then
  echo "环境配置文件：正常"
else
  echo "提醒：未找到 .env，请先从 .env.example 复制并完成配置。"
fi

python - <<'PY'
modules = [
    "fastapi",
    "sqlalchemy",
    "apscheduler",
    "openai",
    "requests",
]

missing = []
for module in modules:
    try:
        __import__(module)
    except Exception:
        missing.append(module)

if missing:
    print("缺少 Python 模块：", ", ".join(missing))
    raise SystemExit(1)

print("Python 依赖：正常")
PY

python -m app.cli check

echo "安装检查完成"

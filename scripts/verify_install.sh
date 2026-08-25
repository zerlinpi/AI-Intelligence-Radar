#!/usr/bin/env bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "== AI Intelligence Radar Installation Check =="

if ! command -v python >/dev/null 2>&1; then
  echo "Python is required"
  exit 1
fi

python --version

if [ -f .env ]; then
  echo "Environment file: OK"
else
  echo "Warning: .env not found. Copy .env.example to .env first."
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
    print("Missing modules:", ", ".join(missing))
    raise SystemExit(1)

print("Python dependencies: OK")
PY

python -m app.cli check

echo "Installation check completed successfully"

#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "[ERROR] 缺少 .env；请先按 .env.example 配置生产环境。" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "[ERROR] 工作区存在未提交修改，拒绝覆盖部署。" >&2
  git status --short >&2
  exit 1
fi

echo "[1/7] 更新 main..."
git fetch origin main
git checkout main
git pull --ff-only origin main

APP_COMMIT_SHA="$(git rev-parse HEAD)"
export APP_COMMIT_SHA
echo "目标版本: $APP_COMMIT_SHA"

echo "[2/7] 构建 Radar 镜像..."
docker compose build --no-cache radar

echo "[3/7] 重建 Radar 容器..."
docker compose up -d --force-recreate radar

echo "[4/7] 等待 /health..."
attempt=0
while [ "$attempt" -lt 30 ]; do
  if curl -fsS http://127.0.0.1:8000/health >/tmp/ai-radar-health.json 2>/dev/null; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done
if [ "$attempt" -ge 30 ]; then
  echo "[ERROR] 60 秒内 /health 未恢复。" >&2
  docker logs --tail 120 ai-intelligence-radar >&2 || true
  exit 1
fi

echo "[5/7] 验证生产 /ready..."
if ! curl -fsS http://127.0.0.1:8000/ready >/tmp/ai-radar-ready.json; then
  echo "[ERROR] /ready 未通过。" >&2
  cat /tmp/ai-radar-ready.json 2>/dev/null || true
  echo >&2
  docker logs --tail 120 ai-intelligence-radar >&2 || true
  exit 1
fi

echo "[6/7] 验证版本与调度器..."
curl -fsS http://127.0.0.1:8000/status >/tmp/ai-radar-status.json
python - "$APP_COMMIT_SHA" <<'PY'
import json
import sys

expected = sys.argv[1]
with open("/tmp/ai-radar-status.json", "r", encoding="utf-8") as handle:
    status = json.load(handle)

actual = str(status.get("版本") or "")
if actual != expected:
    raise SystemExit(f"[ERROR] 运行版本不匹配：expected={expected} actual={actual}")

if status.get("调度器运行中") is not True:
    raise SystemExit("[ERROR] APScheduler 未运行")

plan = status.get("调度计划") or {}
for name in ("07:35 本地兜底", "08:00 主发布"):
    row = plan.get(name) or {}
    if row.get("已注册") is not True:
        raise SystemExit(f"[ERROR] 调度任务未注册：{name}")
    if not str(row.get("下次执行") or ""):
        raise SystemExit(f"[ERROR] 调度任务缺少下一次执行时间：{name}")

print(f"版本验证通过：{actual}")
print(json.dumps(plan, ensure_ascii=False, indent=2))
PY

echo "[7/7] 最近日志..."
docker logs --tail 80 ai-intelligence-radar

echo "部署验证完成：$APP_COMMIT_SHA"

# AI 情报雷达运行手册

本手册以当前 `main` 生产架构为准。

## 1. 当前生产流程

```text
定时调度 / CLI / API
        ↓
统一 execution lock + production preflight
        ↓
采集 AI 项目 + Amazon / CBP / CPSC / FDA / FCC 情报
        ↓
清洗 / 去重 / 本地评分
        ↓
最多 4 条政策 + 10 个项目
        ↓
DeepSeek V4 Pro 批量深度分析
Thinking=max + SSE
        ↓
SQLite 在线备份
        ↓
SQLite 保存完整成功分析
        ↓
Decision Model → Feishu Card Builder
        ↓
飞书持久化 Outbox
        ↓
摘要 / 合规 / 产品机会卡片
```

业务文案不设置飞书字符硬上限；单卡超过 Payload 安全预算时自动分页，不截断正文。

---

## 2. 核心生产配置

推荐：

```env
GITHUB_TOKEN=
PRODUCT_HUNT_TOKEN=

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_MAX_TOKENS=131072
LLM_TIMEOUT_SECONDS=900

FEISHU_WEBHOOK=
FEISHU_MAX_PAYLOAD_BYTES=18432
FEISHU_PROJECTS_PER_CARD=5
FEISHU_MAX_RETRIES=3
FEISHU_SEND_TIMEOUT_SECONDS=10
FEISHU_OUTBOX_DIR=./data/feishu-outbox

DATABASE_URL=sqlite:///./data/radar.db
DATABASE_BACKUP_DIR=./data/backups
DATABASE_BACKUP_RETENTION=7
DATA_MIN_FREE_MB=256

RUN_HISTORY_FILE=./data/run-history.json
RUN_HISTORY_LIMIT=100

REPORT_TIMEZONE=Asia/Shanghai
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

说明：

- `LLM_MAX_TOKENS=131072` 是默认 completion 上限，不是固定消耗；代码最高允许 `384000`。
- `LLM_TIMEOUT_SECONDS=900` 为单次模型请求最长 15 分钟。
- `PRODUCT_HUNT_TOKEN`、`GITHUB_TOKEN` 为可选；未配置不会阻止主流程。
- `DATA_MIN_FREE_MB` 只是最低基准。文件型 SQLite 存在时，预检会按数据库实际大小自动提高磁盘安全余量。
- 数据库备份默认保留最近 7 份。

---

## 3. 更新部署

只重建 Radar 服务，不影响服务器上的其他 Docker 服务。

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose build --no-cache radar
docker compose up -d --force-recreate radar
```

不要使用 `docker system prune -a` 等全局清理命令。

---

## 4. 日常检查

### 完整生产预检

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

主要检查：

- SQLite 可连接及 `quick_check`
- 数据库目录、备份目录、Outbox、运行历史可写
- data 所在磁盘剩余空间
- DeepSeek Key / Base URL / Model / Token / Timeout
- 飞书 Webhook 和 Payload 预算
- 报告时区

### 查看服务存活

```bash
curl http://127.0.0.1:8000/health
```

`/health` 仅表示进程存活，也是 Docker healthcheck 使用的接口。

### 查看生产就绪状态

```bash
curl -i http://127.0.0.1:8000/ready
```

只有调度器运行且 production preflight 通过才返回 HTTP 200。

### 查看轻量运行状态

```bash
curl http://127.0.0.1:8000/status
```

或：

```bash
docker exec ai-intelligence-radar python -m app.cli status
```

可查看：

- 最近一次执行状态
- 项目 / 政策数量
- AI fallback 数量
- 飞书是否完成
- 待补发 Outbox 数量
- SQLite 备份数量

运行历史不会保存 API Key、Webhook、完整项目正文或项目 URL。

---

## 5. 手动执行一次日报

```bash
docker exec ai-intelligence-radar python -m app.cli run
```

保存日志：

```bash
set -o pipefail
docker exec ai-intelligence-radar python -m app.cli run 2>&1 | tee /root/radar-manual.log
echo "退出码=${PIPESTATUS[0]}"
```

状态含义：

- `success`：分析、保存、飞书发送达到预期。
- `partial`：存在 AI fallback、保存不完整或飞书已入队待补发。
- `failed`：生产预检、数据库等关键阶段失败。
- `skipped`：已有任务正在运行，本轮未重复执行。

CLI 的 `partial / failed` 会返回非 0 退出码。

---

## 6. 飞书通知恢复

飞书卡片发送前会先写入：

```text
./data/feishu-outbox/
```

如果网络中断或容器重启，下一次会按原顺序补发未完成卡片。

只补发飞书，不重新采集、不调用 DeepSeek：

```bash
docker exec ai-intelligence-radar python -m app.cli flush
```

如果 Outbox JSON 损坏，会移动到：

```text
./data/feishu-outbox/bad/
```

不会永久阻塞后续队列。

---

## 7. 数据库保护与恢复

### 自动备份

每轮真正进入数据库写入前，文件型 SQLite 会通过原生 backup API 创建一致性备份：

```text
./data/backups/radar-YYYYMMDDTHHMMSS....db
```

备份会执行 `PRAGMA quick_check`，并按 `DATABASE_BACKUP_RETENTION` 自动清理旧文件。

查看：

```bash
ls -lh /opt/AI-Intelligence-Radar/data/backups
```

### 手动恢复

恢复数据库是破坏性操作，只在确认当前数据库需要回退时执行。先停止 **Radar 单个服务**：

```bash
cd /opt/AI-Intelligence-Radar
docker compose stop radar
```

先备份当前文件：

```bash
cp data/radar.db data/radar.db.before-restore
```

确认目标备份文件后再复制，例如：

```bash
cp data/backups/radar-目标时间.db data/radar.db
rm -f data/radar.db-wal data/radar.db-shm
docker compose up -d radar
```

恢复后检查：

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

不要对服务器上的 Nextcloud、MariaDB、Redis 做任何停止或清理操作。

---

## 8. 常见故障

### DeepSeek 超时

先看真实耗时和模型配置：

```bash
docker exec -i ai-intelligence-radar python - <<'PY'
from app.config import LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS
print(LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS)
PY
```

当前 DeepSeek 使用 SSE 内部流式接收；长时间 Thinking 不会要求终端持续输出最终 JSON。

如果日志出现 `finish_reason=length`，再考虑把 `LLM_MAX_TOKENS` 提高到 `262144`；不要仅因为输出变长就直接开到模型最大值。

### 飞书失败

```bash
docker exec ai-intelligence-radar python -m app.cli status
docker exec ai-intelligence-radar python -m app.cli flush
```

429 / 5xx / 网络错误会重试；不可恢复 4xx 不会盲目重复请求。

### 数据库锁

当前 SQLite 已启用：

```text
WAL
busy_timeout=15000ms
connection timeout=15s
```

如果仍出现 `database is locked`，先确认是否有非项目脚本直接持有 `radar.db` 写锁。

### 磁盘空间不足

```bash
df -h /opt/AI-Intelligence-Radar/data
du -sh /opt/AI-Intelligence-Radar/data/*
```

Docker stdout 日志已经设置：

```text
max-size=10m
max-file=5
```

不要用全局 Docker prune 解决本项目磁盘问题。

---

## 9. 推荐日常维护

每天或出现异常时优先执行：

```bash
docker exec ai-intelligence-radar python -m app.cli status
docker exec ai-intelligence-radar python -m app.cli check
```

确认：

```text
最近执行 status=success
AI降级=0
飞书待补发队列=0
数据库备份数量>0
/ready = HTTP 200
```

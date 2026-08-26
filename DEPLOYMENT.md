# AI 情报雷达部署说明

## 环境要求

- Docker + Docker Compose
- 飞书自定义机器人 Webhook
- DeepSeek 或其他兼容 OpenAI 接口格式的模型密钥
- 默认 SQLite 持久化到 `./data`

生产服务只绑定：

```text
127.0.0.1:8000
```

## 核心环境变量

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

`GITHUB_TOKEN` 和 `PRODUCT_HUNT_TOKEN` 为可选数据源配置；其他生产核心项由 `python -m app.cli check` 验证。

---

## 首次部署 / 更新

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose build --no-cache radar
docker compose up -d --force-recreate radar
```

只操作 Compose service `radar`。不要使用全局 Docker 清理命令，也不要重启无关服务。

Docker Compose 已配置：

- `restart: unless-stopped`
- `init: true`
- `/health` liveness healthcheck
- Docker stdout 日志 `10 MB × 5` 轮转
- `./data:/app/data` 持久化数据库、备份、Outbox 和运行历史

---

## 部署后验证

### 1. 配置与本地生产依赖

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

### 2. 容器存活

```bash
curl http://127.0.0.1:8000/health
```

### 3. 生产就绪

```bash
curl -i http://127.0.0.1:8000/ready
```

期望：

```text
HTTP/1.1 200 OK
```

### 4. 运行状态

```bash
docker exec ai-intelligence-radar python -m app.cli status
```

或：

```bash
curl http://127.0.0.1:8000/status
```

---

## 手动执行一次完整日报

```bash
set -o pipefail
docker exec ai-intelligence-radar python -m app.cli run 2>&1 | tee /root/radar-manual.log
echo "退出码=${PIPESTATUS[0]}"
```

完整流程：

```text
统一预检
→ 采集 / 清洗 / 去重
→ 本地评分
→ DeepSeek V4 Pro max-thinking 批量分析
→ SQLite 在线备份
→ SQLite 保存成功分析
→ Decision Model / Card Builder
→ 飞书持久化 Outbox
→ 多卡/分页发送
```

飞书正文不设置业务字符硬上限；超过单卡 Payload 预算会自动分页。

---

## 飞书补发

只恢复 Outbox，不重新运行采集和 DeepSeek：

```bash
docker exec ai-intelligence-radar python -m app.cli flush
```

查看待补发数量：

```bash
docker exec ai-intelligence-radar python -m app.cli status
```

---

## SQLite 备份

每轮进入数据库写入前自动创建一致性备份：

```text
./data/backups/radar-*.db
```

默认保留最近 7 份。创建新备份前会先清理超过保留策略的旧备份，降低磁盘满风险。

生产预检还会根据当前数据库大小动态提高最低剩余空间要求：

```text
max(DATA_MIN_FREE_MB, database_size × 2 + 64 MB)
```

数据库恢复步骤见 `RUNBOOK.md`。

---

## API

- `GET /health`：进程存活检查。
- `GET /ready`：生产可执行性检查。
- `GET /status`：最近执行、Outbox 与备份轻量状态。
- `POST /run`：手动执行一次完整日报；不要暴露到公网。

CLI / API / Scheduler 共用同一套 `run_daily_radar()` execution lock 和 production preflight，避免入口规则不一致。

---

## 禁止事项

不要执行：

```text
docker system prune -a
```

不要因为 Radar 故障停止或删除服务器上的 Nextcloud、MariaDB、Redis 等其他业务容器。

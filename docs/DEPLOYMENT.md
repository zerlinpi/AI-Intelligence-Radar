# AI 情报雷达部署说明

## 生产目标

生产链路采用：

```text
07:35 Asia/Shanghai
常驻 APScheduler 预生成当天本地兜底
        ↓
08:00
常驻服务主发布
        ↓
08:06
GitHub Actions 灾备检查
```

GitHub Actions 不是 08:00 主时钟；服务器上的常驻容器必须保持运行并使用最新 `main`。

## 必需环境变量

```env
FEISHU_WEBHOOK=

RADAR_GITHUB_REPOSITORY=zerlinpi/AI-Intelligence-Radar
RADAR_GITHUB_TOKEN=
CHATGPT_FEED_ISSUE=2
CHATGPT_FEED_AUTHOR=zerlinpi

REPORT_TIMEZONE=Asia/Shanghai
RADAR_FALLBACK_PREP_HOUR=7
RADAR_FALLBACK_PREP_MINUTE=35
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
RADAR_ENFORCE_SEND_WINDOW=1
RADAR_SEND_WINDOW_START=08:00
RADAR_SEND_WINDOW_END=08:10
RADAR_LOCAL_FALLBACK_PATH=./data/local-fallback-cards.json
RADAR_PUBLISH_LOCK_FILE=./data/radar-publish.lock

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro

DATABASE_URL=sqlite:///./data/radar.db
FEISHU_OUTBOX_DIR=./data/feishu-outbox
```

`RADAR_GITHUB_TOKEN` 是 08:00 主发布器的生产必需项，用于读取 Issue #2 Feed 和写 delivery receipt。建议使用仅限本仓库、Issues Read/Write 的 fine-grained token。

`GITHUB_TOKEN` 仍可用于项目采集，但不能把“采集 token 可选”误解成“08:00 发布协调 token 可选”。

## 推荐更新方式

不要只执行 `git pull`。使用仓库自带的验证部署脚本：

```bash
cd /opt/AI-Intelligence-Radar
git fetch origin main
git checkout main
git pull --ff-only origin main
sh scripts/deploy_radar.sh
```

脚本会：

1. 拒绝有未提交修改的工作区。
2. 要求当前分支为 `main`。
3. `git fetch origin main` 并验证当前 HEAD 已等于 `origin/main`；脚本运行中不会自行修改代码。
4. 将当前 Git SHA 写入 Docker 镜像。
5. 重建并重启仅 `radar` 服务。
6. 等待 `/health`。
7. 要求 `/ready` 返回 200。
8. 检查运行容器版本与 Git HEAD 完全一致。
9. 验证 `07:35 本地兜底` 和 `08:00 主发布` 两个任务都已注册。

## 手动更新方式

如需手动操作：

```bash
cd /opt/AI-Intelligence-Radar
git fetch origin main
git checkout main
git pull --ff-only origin main
export APP_COMMIT_SHA="$(git rev-parse HEAD)"
docker compose build --no-cache radar
docker compose up -d --force-recreate radar
```

随后必须验证：

```bash
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/status
```

`/health`、`/ready` 和 `/status` 都会返回当前容器的 `版本` Git SHA。

## 正常生产状态

`/ready` 应返回：

```text
HTTP/1.1 200 OK
```

`/status` 至少应满足：

- `版本` 等于服务器当前 `git rev-parse HEAD`
- `调度器运行中 = true`
- `07:35 本地兜底.已注册 = true`
- `08:00 主发布.已注册 = true`
- 两个任务均有下一次执行时间
- 飞书 Outbox 不持续增长

## 容器重启恢复

- 07:35–08:00 之间启动：自动补生成当天 fallback。
- 08:00–08:10 之间启动：自动进入幂等发布恢复。
- 08:10 后：自动流程禁止补发旧日报或旧告警。
- 发布前若当天 fallback 缺失或损坏，会现场补生成。

## 飞书可靠性

发送采用持久化 Outbox：

```text
卡片生成
→ data/feishu-outbox
→ 顺序发送
→ 每张成功后落盘
→ 全部完成后删除队列
```

网络 timeout、HTTP 429/5xx 会重试；已开始发送后若交付状态不确定，不会切换另一套 fallback 重发。

手动只恢复 Outbox：

```bash
docker exec ai-intelligence-radar python -m app.cli flush
```

## API

- `GET /health`：进程、调度器、部署版本。
- `GET /ready`：生产依赖与发布协调是否完整。
- `GET /status`：版本、调度计划、最近运行、采集器、Outbox、数据库备份。
- `POST /run`：手动执行完整分析流程；不要暴露到公网。

服务默认只绑定：

```text
127.0.0.1:8000
```

## 禁止事项

不要执行会影响服务器其他业务容器的全局 Docker 清理：

```text
docker system prune -a
```

只操作 Compose service `radar`。

# AI Intelligence Radar

> 面向“刚上线、正在快速升温”的 AI 项目与产品的自动化情报雷达。
>
> 系统自动采集公开数据，计算早期增长热度，通过 DeepSeek / OpenAI Compatible LLM 生成中文分析，并写入 SQLite、推送飞书日报。

## 当前目标

本项目当前优先完成和稳定以下核心链路，不以“历史累计最热门项目”为目标：

```text
发现近期上线 AI 项目
        ↓
计算单位时间增长速度
        ↓
筛选早期热点 Top 10
        ↓
LLM 中文机会分析
        ↓
SQLite 持久化
        ↓
飞书中文日报
```

“新项目热度”强调上线后的早期增长速度，不等同于历史累计 Stars、Votes 或 Downloads。

---

## 数据源

当前已有数据源：

- **GitHub**：最近 7 天新建的 AI / LLM / AI Agent 项目，综合 Stars、Forks 与上线时间判断增长速度。
- **Hacker News / Show HN**：近期发布的 AI 项目，综合 Votes、Comments 与发布时间判断早期热度。
- **Hugging Face**：最近 7 天新发布模型，综合 Downloads、Likes 与发布时间判断增长速度。
- **arXiv**：最新 cs.AI / cs.LG / cs.CL 研究论文。
- **Product Hunt**：近期 AI 产品，综合 Votes、Comments 与发布时间判断早期热度。需要 `PRODUCT_HUNT_TOKEN`。

所有来源最终统一转换为 `RadarItem`。

---

## 早期热度评分

当前评分重点：

- 新鲜度
- Stars / 天、Votes / 天、Downloads / 天等增长速度
- Forks、Comments、Likes 等早期互动
- 数据源自身 Momentum 信号

当前只进入报告的项目再调用 LLM，避免对全部采集结果逐条请求模型。

默认日报最多输出 **10 条**。

---

## LLM

支持 OpenAI Compatible 接口，包括：

- DeepSeek
- OpenAI
- 其他兼容 OpenAI Chat Completions 的服务

DeepSeek 示例：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=1200
```

LLM 请求使用受控重试：401/403/404 等不可恢复配置错误会立即失败并使用 fallback；网络错误、429、5xx 等临时错误才会重试。

---

## 飞书通知

配置：

```env
FEISHU_WEBHOOK=https://open.feishu.cn/...
```

日报为全中文，主要包含：

- 项目名称和来源
- 大致上线时间
- 新项目热度
- Stars / Votes / Downloads 等早期指标
- 单位时间增长速度
- 商业机会等级和商业分
- AI 中文判断
- 首个可关注机会点
- 项目链接

---

## 环境变量

复制样例：

```bash
cp .env.example .env
```

核心配置：

```env
GITHUB_TOKEN=
PRODUCT_HUNT_TOKEN=

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=1200

FEISHU_WEBHOOK=
DATABASE_URL=sqlite:///./data/radar.db

RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

说明：

- `GITHUB_TOKEN`：可选；不配置时 GitHub API 速率限制更低。
- `PRODUCT_HUNT_TOKEN`：可选；不配置时 Product Hunt Collector 会跳过并记录 WARN。
- `LLM_API_KEY`：日报 AI 分析必需。
- `FEISHU_WEBHOOK`：飞书推送必需。
- `DATABASE_URL`：Docker 默认使用 `./data/radar.db` 持久化。
- Scheduler 当前时区为 `Asia/Shanghai`（UTC+8）。

---

# Docker 部署

生产环境推荐使用 Docker Compose。

## 首次部署 / 更新

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose up -d --build
```

查看状态：

```bash
docker ps
```

正常应看到：

```text
ai-intelligence-radar   Up ... (healthy)
```

API 默认只绑定宿主机本地地址：

```text
127.0.0.1:8000->8000/tcp
```

不会默认暴露到公网。

---

## 配置自检

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

必需项：

```text
[OK] Database
[OK] Feishu Webhook
[OK] LLM API Key
[OK] LLM Model
[OK] LLM Base URL
```

可选项未配置时显示 `WARN`：

```text
[WARN] GitHub Token
[WARN] Product Hunt Token
```

可选项 WARN 不会阻止主程序运行。

---

## 健康检查

进程存活：

```bash
curl http://localhost:8000/health
```

Scheduler 就绪：

```bash
curl -i http://localhost:8000/ready
```

正常 Scheduler 运行时 `/ready` 返回 HTTP 200；未就绪时返回 HTTP 503，因此 Docker healthcheck 能真实反映服务状态。

---

## 手动运行完整日报

推荐直接从宿主机执行：

```bash
docker exec ai-intelligence-radar python -m app.cli
```

保留完整日志：

```bash
docker exec ai-intelligence-radar python -m app.cli 2>&1 | tee /root/radar-test.log
```

完整流程：

```text
Collectors
   ↓
Normalize / Deduplicate
   ↓
Early Momentum Score
   ↓
Top 10
   ↓
DeepSeek / OpenAI Compatible Analysis
   ↓
SQLite
   ↓
Feishu
```

如果手动运行与 Scheduler 正在执行的任务重叠，系统会主动跳过第二次执行，避免重复调用 LLM、重复写库和重复发飞书。

---

## 日志

```bash
docker logs --tail 100 ai-intelligence-radar
```

持续查看：

```bash
docker logs -f ai-intelligence-radar
```

关键成功日志通常包括：

```text
collector=GithubCollector items=...
collector=HackerNewsCollector items=...
collector=HuggingFaceCollector items=...
collector=ArxivCollector items=...
collector=ProductHuntCollector items=...
saved=...
feishu sent
daily radar finished
```

Product Hunt 正常执行时还会记录：

```text
product hunt fetched=... recent_ai=...
```

---

## 数据库

Docker Compose 挂载：

```text
./data:/app/data
```

默认数据库：

```text
./data/radar.db
```

数据库保存来源项目真实发布时间，用于后续判断项目年龄和早期增长速度。

容器启动时会先执行数据库迁移脚本，再启动 FastAPI。

---

# API

## `GET /health`

确认 FastAPI 进程存活。

## `GET /ready`

确认 Scheduler 已启动。

- Ready：HTTP 200
- Not Ready：HTTP 503

## `POST /run`

手动执行一次完整 Radar 流程。

Docker 默认只将 API 绑定到 `127.0.0.1:8000`，避免未经授权的公网请求触发 LLM 和飞书。

---

# Scheduler

默认：

```text
每天 08:00
Timezone: Asia/Shanghai
```

可配置：

```env
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

非法小时或分钟不会导致容器直接启动失败，系统会回退到默认值并记录警告。

---

# 测试

GitHub Actions 会执行：

```bash
python -m pytest -v --tb=short
```

测试范围包括：

- LLM JSON 解析与 fallback
- LLM 临时错误重试 / 不可恢复错误快速失败
- 数据清洗与去重
- RadarItem 转换
- 新项目评分
- SQLite 存储
- 来源发布时间持久化
- 飞书发送
- Product Hunt 近期 AI 产品过滤
- `/ready` 200 / 503
- 防止重复并发执行

---

# 项目目录

```text
app/
├── ai/              # LLM 分析、解析、重试
├── core/            # 日志、执行锁
├── database/        # SQLAlchemy 数据库
├── models/          # RadarItem
├── sources/         # GitHub / HN / HF / arXiv / Product Hunt
├── storage/         # SQLite 存储
├── pipeline.py      # 核心日报流程
├── scheduler.py     # APScheduler
├── main.py          # FastAPI
└── feishu.py        # 飞书通知

scripts/
├── migrate_db.py
├── docker-entrypoint.sh
└── verify_install.sh
```

---

# 当前阶段

当前优先级是继续稳定现有核心能力：

- 新项目发现准确性
- 增长速度评分质量
- LLM 分析稳定性
- 数据持久化可靠性
- 飞书日报可读性
- Docker / Scheduler 长期运行稳定性

在这些核心能力完成并经过真实环境验证之前，不优先扩展 Dashboard、趋势可视化或其他新模块。

---

# License

MIT

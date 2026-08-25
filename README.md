# AI Intelligence Radar

> AI 情报自动化系统
>
> 自动采集 AI 领域公开信息，通过趋势评分、LLM 分析生成每日情报，并推送到飞书。

## 项目定位

AI Intelligence Radar 是一个自动化 AI 情报系统，面向：

- AI 开发者
- 创业团队
- 技术研究人员
- 投资与市场分析人员

核心目标：

```
发现 AI 信号
        ↓
理解技术价值
        ↓
判断商业机会
        ↓
生成每日行动建议
```

---

# 系统架构

```
                 Data Sources

 GitHub | HackerNews | HuggingFace | arXiv | Product Hunt

                         ↓

                Collector Layer

                         ↓

                  RadarItem Model

                         ↓

              Cleaning + Deduplication

                         ↓

                Radar Score Engine

                         ↓

          LLM Intelligence Layer

       OpenAI Compatible / DeepSeek

                         ↓

              SQLite Historical DB

                         ↓

                Feishu Daily Report
```

---

# 核心模块说明

## Collector

负责采集外部 AI 信息。

当前支持：

- GitHub AI 项目
- Hacker News 技术趋势
- HuggingFace 模型动态
- arXiv AI 论文
- Product Hunt 产品信号

所有数据统一转换为 RadarItem。

---

## Radar Score Engine

综合：

- 社区热度
- 开发活跃度
- AI 相关性
- 市场信号
- 时间新鲜度

生成趋势评分。

---

## AI Intelligence Layer

支持所有 OpenAI Compatible API。

包括：

- OpenAI
- DeepSeek
- 本地兼容 OpenAI API 的模型服务

配置：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

---

# 飞书通知

系统自动生成：

- 今日 AI 热点
- 技术价值分析
- 商业机会判断
- 创业方向建议

配置：

```env
FEISHU_WEBHOOK=https://open.feishu.cn/...
```

---

# 本地运行

## 1. 克隆项目

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git
cd AI-Intelligence-Radar
```

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 配置环境变量

```bash
cp .env.example .env
```

修改：

- LLM API Key
- DeepSeek/OpenAI 配置
- 飞书 Webhook

## 4. 测试环境

```bash
make check
make test
```

## 5. 启动服务

```bash
make run
```

---

# Docker 部署

推荐生产环境使用 Docker：

```bash
docker compose build
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

检查服务：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

# API接口

## Health Check

```
GET /health
```

用于 Docker 和服务监控。

## Ready Check

```
GET /ready
```

用于确认 Scheduler 是否正常运行。

## 手动执行日报

```
POST /run
```

立即执行一次完整 AI Radar 流程。

---

# 自动任务

系统内置 Scheduler。

默认：

```
每天 08:00
```

可通过环境变量调整：

```env
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

---

# 当前完成能力

✅ 多源 AI 情报采集

✅ Collector 统一架构

✅ RadarItem 数据模型

✅ 数据清洗与去重

✅ 趋势评分系统

✅ DeepSeek/OpenAI Compatible LLM

✅ AI 商业机会分析

✅ SQLite 历史存储

✅ 数据库自动迁移

✅ Docker 自动部署

✅ Scheduler 自动运行

✅ 飞书机器人通知

✅ Retry 与异常恢复

✅ 基础 CI 测试

---

# 项目目录

```
app/
├── ai/              # LLM分析
├── core/            # 配置和日志
├── database/        # 数据库模型
├── models/          # Radar数据模型
├── sources/         # 数据采集器
├── storage/         # 数据存储
├── pipeline.py      # 核心流程
├── scheduler.py     # 定时任务
└── feishu.py        # 飞书通知

scripts/
├── migrate_db.py
└── docker-entrypoint.sh
```

---

# 开发路线

## Phase 1

当前版本目标：

- 稳定每日 AI 情报
- 飞书自动推送
- 完整生产部署

## Phase 2

计划：

- Dashboard
- 趋势可视化
- 更多数据源

## Phase 3

计划：

- 行业 AI 雷达
- API 服务
- 个性化情报订阅

---

# License

MIT

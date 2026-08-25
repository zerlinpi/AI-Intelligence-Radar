# AI Intelligence Radar

> AI 情报自动化系统
>
> 自动采集 AI 领域公开信息，通过趋势评分与 LLM 分析生成每日情报，并推送到飞书。

## 项目定位

AI Intelligence Radar 是一个面向开发者、创业者和研究人员的 AI 趋势发现系统。

系统自动收集：

- GitHub 热门 AI 项目
- Hacker News 技术趋势
- HuggingFace 模型动态
- 后续扩展 Product Hunt / arXiv

通过 LLM 分析，将原始信息转换为：

- 技术价值判断
- 热度趋势判断
- 商业机会分析
- 每日飞书情报日报

---

# 系统架构

```
Data Collection

GitHub / HackerNews / HuggingFace

        ↓

Data Cleaning

        ↓

Duplicate Filtering

        ↓

Trend Scoring Engine

        ↓

LLM Intelligence Layer

(OpenAI Compatible / DeepSeek)

        ↓

SQLite Historical Storage

        ↓

Feishu Daily Report
```

---

# LLM 支持

当前支持所有 OpenAI Compatible API：

- OpenAI
- DeepSeek
- 本地模型服务（例如兼容 OpenAI API 的部署）

配置示例：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

---

# 快速启动

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git
cd AI-Intelligence-Radar
pip install -r requirements.txt
cp .env.example .env
```

修改 `.env` 后：

```bash
make check
make test
make run
```

---

# Docker 部署

```bash
docker compose up -d
```

检查：

```bash
docker compose logs -f
```

---

# 每日报告流程

```
Collector
   ↓
Cleaner
   ↓
Scoring
   ↓
LLM Analysis
   ↓
Database
   ↓
Feishu Bot
```

---

# 当前完成能力

- 多源 AI 信息采集
- 数据清洗与去重
- 趋势评分
- LLM 分析接口
- DeepSeek/OpenAI Compatible 支持
- 飞书机器人推送
- SQLite历史存储
- Docker部署
- Scheduler自动任务
- CI测试基础设施

---

# Roadmap

## Phase 1

- 稳定每日飞书日报
- 完善数据源
- 提升评分模型

## Phase 2

- Product Hunt
- arXiv论文
- Dashboard
- 趋势图表

## Phase 3

- AI创业机会分析
- 行业雷达
- API服务

---

# License

MIT

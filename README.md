# AI Intelligence Radar

> AI 创业情报自动化系统
>
> 自动发现正在增长的 AI 项目、技术趋势和商业机会，并通过 LLM 分析后生成飞书日报。

---

## 项目介绍

AI Intelligence Radar 是一个面向开发者、创业者和产品研究人员的 AI 情报系统。

系统每天自动收集多个公开数据源：

- GitHub Trending / 高增长项目
- Product Hunt 新产品
- Hacker News 技术趋势
- arXiv AI 论文
- HuggingFace 热门模型

经过数据清洗、去重、评分和 AI 分析后，输出：

- 技术趋势判断
- 热度评分
- 商业价值分析
- 可创业方向建议
- 飞书日报推送

---

# 系统架构

```
                    Data Collection Layer

 ┌────────────┬────────────┬────────────┬────────────┬────────────┐
 GitHub       Product      Hacker       AI           HuggingFace
 Trending     Hunt         News         Papers       Models
 └────────────┴────────────┴────────────┴────────────┴────────────┘

                         ↓

              Data Cleaning & Deduplication

                         ↓

                    AI Analysis Layer

              ┌──────────────────────┐
              │  LLM Intelligence     │
              └──────────────────────┘

                         ↓

        ┌────────────────┴────────────────┐
        ↓                                 ↓
 Trend Score                    Business Analysis

                         ↓

                 Daily Report Generator

                         ↓

                    Feishu Bot
```

---

# 技术栈

## Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- SQLite / PostgreSQL
- APScheduler

## AI

- OpenAI Compatible API
- LLM structured analysis
- Opportunity scoring model

## Integration

- Feishu Bot Webhook
- GitHub Actions
- Docker

---

# 已完成功能

## 数据采集层

- [x] GitHub 数据源结构
- [x] Product Hunt 数据源结构
- [x] Hacker News 数据源结构
- [x] arXiv AI Papers 数据源结构
- [x] HuggingFace Models 数据源结构

## 数据处理

- [x] 数据标准化
- [x] 数据清洗
- [x] URL 去重
- [x] 历史记录保存结构

## AI 分析

- [x] 热度评分模型
- [x] 商业机会分析框架
- [x] LLM 分析接口

## 通知系统

- [x] 飞书机器人接口
- [x] 日报生成结构

## 工程化

- [x] FastAPI 服务
- [x] Docker 部署结构
- [x] GitHub Actions 自动任务结构

---

# 项目运行

## 1. 克隆项目

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git

cd AI-Intelligence-Radar
```

---

## 2. 创建环境变量

复制：

```bash
cp .env.example .env
```

配置：

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5-mini
FEISHU_WEBHOOK=your_feishu_webhook
GITHUB_TOKEN=your_github_token
DATABASE_URL=sqlite:///radar.db
```

---

## 3. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 4. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问：

```
http://localhost:8000/health
```

返回：

```json
{
  "ok": true
}
```

---

# Docker 部署

```bash
docker compose up -d
```

服务启动后会自动运行 Radar 服务。

---

# 手动执行日报任务

调用：

```
POST /run
```

执行流程：

```
Collect
 ↓
Clean
 ↓
Score
 ↓
LLM Analysis
 ↓
Generate Report
 ↓
Feishu Push
```

---

# 飞书配置

1. 创建飞书群机器人
2. 获取 Webhook 地址
3. 设置：

```env
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
```

系统会自动发送 AI Radar 日报。

---

# 日报示例

```
🔥 AI Intelligence Radar Daily

Project:
OpenHands

Source:
GitHub

Trend Score:
92

Business Score:
88

Analysis:
AI Coding Agent 方向持续增长。

Opportunity:
Enterprise AI Developer Tool
```

---

# Roadmap

## Phase 1

- [x] Data source architecture
- [x] Scoring engine
- [x] LLM analysis framework
- [x] Feishu notification

## Phase 2

- [ ] Production database migration
- [ ] Complete API collectors
- [ ] Dashboard
- [ ] Trend prediction model

## Phase 3

- [ ] Multi-user intelligence platform
- [ ] Custom industry radar
- [ ] AI investment research assistant

---

# License

MIT

# AI Intelligence Radar

> AI 情报自动化系统
>
> 自动采集 AI 领域公开信息，通过规则评分与 LLM 分析生成每日情报，并推送到飞书。

## 项目目标

本项目解决的问题：

- 每天发现值得关注的 AI 项目
- 跟踪开源趋势和产品机会
- 自动分析技术价值与商业潜力
- 降低人工研究成本

当前第一阶段目标：

```
数据采集
    ↓
数据整理
    ↓
趋势评分
    ↓
AI分析
    ↓
飞书日报通知
```

---

# 系统架构

```
                    Data Collection Layer

 ┌──────────┬────────────┬──────────┬──────────┬────────────┐
 GitHub     Product      Hacker     AI        HuggingFace
 Projects   Hunt         News       Papers    Models
 └──────────┴────────────┴──────────┴──────────┴────────────┘

                         ↓

              Data Cleaning & Normalization

                         ↓

                 Trend Scoring Engine

                         ↓

                  LLM Analysis Layer

              ┌──────────────────────┐
              │ Technology Analysis  │
              │ Business Opportunity│
              └──────────────────────┘

                         ↓

                 Report Generator

                         ↓

                    Feishu Bot
```

---

# 技术栈

## Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- APScheduler

## AI

- OpenAI Compatible API
- LLM analysis
- Opportunity evaluation

## Deployment

- Docker
- GitHub Actions
- Feishu Webhook

---

# 当前实现状态

## 已完成

### 基础服务

- FastAPI 服务入口
- Health Check
- 手动任务执行接口

### 数据处理

- 数据采集模块结构
- 数据清洗流程
- 评分模块

### AI能力

- LLM 调用接口
- AI项目分析框架

### 通知

- 飞书机器人 Interactive Card
- 日报消息生成

### 工程化

- Docker 部署结构
- 环境变量配置

---

# 快速启动

## 1. Clone

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git
cd AI-Intelligence-Radar
```

## 2. 创建环境变量

```bash
cp .env.example .env
```

配置：

```env
OPENAI_API_KEY=
OPENAI_MODEL=
FEISHU_WEBHOOK=
GITHUB_TOKEN=
DATABASE_URL=sqlite:///radar.db
```

## 3. 安装依赖

```bash
pip install -r requirements.txt
```

## 4. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

检测：

```
GET /health
```

---

# 手动生成日报

调用：

```
POST /run
```

执行：

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
2. 获取 Webhook
3. 添加：

```env
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

运行后会自动推送日报。

---

# Docker运行

```bash
docker compose up -d
```

---

# 项目目录

```
app/

├── sources/       # 数据源
├── ai/            # LLM分析
├── reports/       # 日报生成
├── database/      # 数据模型
├── storage/       # 数据保存
├── scheduler.py   # 定时任务
├── pipeline.py    # 数据流程
└── feishu.py      # 飞书通知
```

---

# 后续规划

## Phase 1

- 完善真实 API Collector
- 完善数据统一模型
- 增强异常处理
- 增加自动化测试

## Phase 2

- 历史趋势分析
- Dashboard
- 更多数据源

## Phase 3

- 多行业情报雷达
- AI投资研究助手

---

# License

MIT

# AI Intelligence Radar

> AI 情报自动化系统
>
> 自动采集 AI 领域公开信息，通过趋势评分与 LLM 分析生成每日情报，并推送到飞书。

## 项目目标

AI Intelligence Radar 是一个自动化 AI 情报系统，用于每天发现：

- GitHub 高热度开源项目
- Hacker News 技术趋势
- HuggingFace 新模型
- AI 商业机会

最终输出：

```
数据采集
    ↓
数据清洗
    ↓
重复过滤
    ↓
趋势评分
    ↓
LLM 分析
    ↓
日报生成
    ↓
飞书机器人通知
```

---

# 当前系统架构

```
Collectors

GitHub
Hacker News
HuggingFace

        ↓

Cleaning & Normalization

        ↓

Duplicate Filter

        ↓

Trend Scoring Engine

        ↓

LLM Analysis

        ↓

SQLite Storage

        ↓

Feishu Daily Report
```

---

# 当前已完成能力

## 数据层

- Collector 模块化架构
- GitHub 数据采集
- Hacker News 数据采集
- HuggingFace 模型采集
- 数据标准化处理
- URL 去重

## AI 分析层

- 趋势评分模型
- LLM 分析接口
- 技术价值分析结构
- 商业机会分析扩展接口

## 通知层

- 飞书机器人 Webhook
- 日报消息生成

## 工程化

- SQLite 数据持久化
- Docker 部署结构
- 环境变量配置
- CLI运行入口

---

# 快速启动

## 安装

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git
cd AI-Intelligence-Radar
pip install -r requirements.txt
```

## 配置环境变量

创建 `.env`：

```env
OPENAI_API_KEY=
OPENAI_MODEL=
FEISHU_WEBHOOK=
GITHUB_TOKEN=
DATABASE_URL=sqlite:///radar.db
```

---

# 运行检查

执行：

```bash
python -m app.cli check
```

检查：

- Environment
- Pipeline
- Database
- Feishu Config

---

# 生成日报

```bash
python -m app.cli
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
Save Database
 ↓
Feishu Push
```

---

# 测试

运行：

```bash
pytest
```

当前覆盖：

- Cleaner
- Scoring
- Storage
- Feishu
- Pipeline

---

# 项目结构

```
app/
├── sources/       数据采集
├── ai/            LLM分析
├── database/      数据库
├── storage/       数据保存
├── reports/       报告生成
├── pipeline.py    核心流程
├── feishu.py      飞书通知
└── cli.py         命令入口
```

---

# Roadmap

## Phase 1

- 完成稳定飞书日报推送
- 增强 Collector
- 增加更多测试

## Phase 2

- Product Hunt
- arXiv论文
- Dashboard
- 历史趋势分析

## Phase 3

- AI创业机会分析
- 行业情报雷达
- 自动投资研究助手

---

# License

MIT

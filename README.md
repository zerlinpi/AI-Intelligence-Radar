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

核心目标：

> 自动发现值得关注的 AI 项目，并通过 AI 分析转化为可执行的情报日报。

---

# 系统架构

```
                Data Collection

 GitHub    HackerNews    HuggingFace

                ↓

       Cleaning & Normalization

                ↓

          Duplicate Filtering

                ↓

          Trend Scoring Model

                ↓

             LLM Analysis

                ↓

          SQLite Historical DB

                ↓

          Daily Report Builder

                ↓

            Feishu Bot Push
```

---

# 当前已完成能力

## 数据采集层

- GitHub 项目采集
- Hacker News 热点采集
- HuggingFace 模型采集
- Collector 模块化设计

## 数据处理层

- 数据标准化
- URL 去重
- 历史数据过滤
- 趋势评分

## AI 分析层

- LLM 分析接口
- 技术价值分析
- 商业机会分析扩展能力

## 通知层

- 飞书机器人 Webhook
- 自动生成日报消息

## 工程化

- SQLite 数据持久化
- CLI运行入口
- Docker支持
- GitHub Actions CI
- 自动化测试
- Makefile统一命令

---

# 快速启动

## 安装

```bash
git clone https://github.com/zerlinpi/AI-Intelligence-Radar.git
cd AI-Intelligence-Radar
pip install -r requirements.txt
```

## 环境变量

创建 `.env`：

```env
OPENAI_API_KEY=
OPENAI_MODEL=
FEISHU_WEBHOOK=
GITHUB_TOKEN=
DATABASE_URL=sqlite:///radar.db
```

---

# 常用命令

## 环境检查

```bash
make check
```

或者：

```bash
python -m app.cli check
```

检查：

- Python环境
- 数据库配置
- LLM配置
- 飞书配置
- Pipeline状态

---

## 自动测试

```bash
make test
```

等价：

```bash
pytest -v --tb=short
```

测试覆盖：

- Cleaner
- Scoring
- Storage
- Feishu(Mock)
- Pipeline

---

## 生成日报

```bash
make run
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

# 部署

详细部署说明：

```
DEPLOYMENT.md
```

生产运行建议：

```
Scheduler
    ↓
Daily Pipeline
    ↓
Feishu Notification
```

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

scripts/
└── verify.py      环境验证

.github/
└── workflows/     CI测试
```

---

# Roadmap

## Phase 1 (完成)

- 稳定飞书日报推送
- AI热点采集
- 趋势评分
- LLM分析
- 自动测试

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

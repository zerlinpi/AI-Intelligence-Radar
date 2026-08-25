# AI Intelligence Radar

AI 情报聚合与机会分析系统。

## Architecture

```
Data Sources
 ├── GitHub Trending
 ├── Product Hunt
 ├── Hacker News
 ├── AI Papers
 └── HuggingFace Models

        ↓

Data Cleaning & Deduplication
        ↓

LLM Analysis Layer
 ├── Trend Score
 └── Business Opportunity Analysis

        ↓

Feishu Daily Report
        ↓

Feishu Bot
```

## Tech Stack

- Python 3.12
- FastAPI (service layer)
- SQLite/PostgreSQL (storage)
- APScheduler (scheduled jobs)
- OpenAI compatible LLM API
- Feishu Bot Webhook
- GitHub Actions deployment

## Roadmap

- [x] Project initialization
- [ ] Data collectors
- [ ] Data normalization
- [ ] Scoring engine
- [ ] LLM analyst
- [ ] Feishu card generator
- [ ] Daily automation

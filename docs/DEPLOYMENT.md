# Deployment Guide

## Local

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker compose up -d
```

## Runtime Flow

1. Scheduler starts daily radar job.
2. Collectors fetch intelligence sources.
3. Cleaner removes duplicates.
4. Scoring engine ranks opportunities.
5. LLM analyzer generates business analysis.
6. Feishu bot sends the daily report.

## Required Services

- GitHub Token
- OpenAI compatible API key
- Feishu Bot Webhook

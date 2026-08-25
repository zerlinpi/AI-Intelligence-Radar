# Deployment Guide

## Requirements

- Python 3.10+
- Feishu Incoming Webhook
- LLM API Key
- SQLite or compatible database

## Environment Variables

```env
DATABASE_URL=sqlite:///radar.db
OPENAI_API_KEY=your_key
FEISHU_WEBHOOK=your_webhook
```

## Local Verification

```bash
python scripts/verify.py
```

## Test

```bash
make test
```

## Run Daily Radar

```bash
make run
```

## Production Flow

Scheduler triggers the pipeline:

Collectors -> Cleaner -> Scoring -> LLM Analysis -> Database -> Feishu Notification

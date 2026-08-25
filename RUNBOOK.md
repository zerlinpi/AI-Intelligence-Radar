# AI Intelligence Radar Runbook

## Daily Production Flow

```
Scheduler
   ↓
Collect AI Signals
   ↓
Normalize & Deduplicate
   ↓
Trend Scoring
   ↓
LLM Analysis
   ↓
Generate Report
   ↓
Send Feishu Notification
```

## Startup Checklist

1. Configure environment variables:

```env
GITHUB_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=
FEISHU_WEBHOOK=
DATABASE_URL=sqlite:///./radar.db
```

2. Validate environment:

```bash
make check
```

3. Run tests:

```bash
make test
```

4. Execute pipeline:

```bash
make run
```

## Troubleshooting

### Feishu notification failed

Check:

- FEISHU_WEBHOOK value
- Network connectivity
- Feishu bot permissions

### LLM analysis failed

Check:

- OPENAI_API_KEY
- OPENAI_MODEL
- API availability

### Duplicate reports

Check SQLite database and historical records.

## Maintenance

Recommended production schedule:

- Run once every morning
- Keep database backups
- Review collector failures periodically

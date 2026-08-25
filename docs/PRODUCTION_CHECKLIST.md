# Production Readiness Checklist

## Environment

- [ ] Configure OpenAI API key
- [ ] Configure GitHub token
- [ ] Configure Feishu webhook
- [ ] Configure database URL

## Runtime

- [ ] Install dependencies
- [ ] Run FastAPI service
- [ ] Verify health endpoint
- [ ] Trigger manual radar execution

## Automation

- [ ] Enable GitHub Actions schedule
- [ ] Verify daily execution
- [ ] Check Feishu notification

## Monitoring

- [ ] Review application logs
- [ ] Monitor API failures
- [ ] Monitor data source availability

## Recommended Production Stack

- Docker
- PostgreSQL
- Cloud Run / Railway / VPS
- GitHub Actions scheduler

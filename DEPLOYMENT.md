# 部署说明

## 环境要求

- Python 3.10+
- 飞书机器人 Webhook
- DeepSeek 或其他兼容 OpenAI 接口格式的模型密钥
- SQLite
- 推荐使用 Docker Compose

## 核心环境变量

```env
DATABASE_URL=sqlite:///./data/radar.db
LLM_PROVIDER=deepseek
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=700
FEISHU_WEBHOOK=你的飞书机器人地址
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

Product Hunt 如需启用：

```env
PRODUCT_HUNT_TOKEN=你的访问令牌
```

## Docker 部署

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose up -d --build
```

检查容器：

```bash
docker ps
```

检查配置：

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

检查服务：

```bash
curl http://localhost:8000/health
curl -i http://localhost:8000/ready
```

## 手动执行日报

```bash
docker exec ai-intelligence-radar python -m app.cli
```

## 当前生产流程

```text
近期项目采集
    ↓
清洗与去重
    ↓
本地早期热度评分
    ↓
选出前 10 项
    ↓
一次 DeepSeek 批量中文分析
    ↓
SQLite 持久化
    ↓
飞书中文通知
```

模型分析会压缩项目简介和指标，只返回短摘要、商业分、机会等级与一条建议，并将单次批量输出限制在 700 Token 以内。

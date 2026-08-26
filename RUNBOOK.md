# AI 情报雷达运行手册

## 每日生产流程

```text
定时调度
   ↓
采集近期 AI 信号
   ↓
清洗与去重
   ↓
本地早期热度评分
   ↓
选出前 10 项
   ↓
一次模型批量分析
   ↓
SQLite 保存
   ↓
飞书中文通知
```

## 启动检查

1. 配置环境变量：

```env
GITHUB_TOKEN=
PRODUCT_HUNT_TOKEN=
LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=700
FEISHU_WEBHOOK=
DATABASE_URL=sqlite:///./data/radar.db
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

2. 检查配置：

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

3. 检查容器：

```bash
docker ps
```

4. 检查服务：

```bash
curl http://localhost:8000/health
curl -i http://localhost:8000/ready
```

5. 手动执行日报：

```bash
docker exec ai-intelligence-radar python -m app.cli
```

## 故障排查

### 飞书通知失败

检查：

- `FEISHU_WEBHOOK` 是否正确
- 服务器网络连接
- 飞书机器人权限
- `docker logs --tail 100 ai-intelligence-radar`

### 模型分析失败

检查：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- DeepSeek 或对应服务是否可访问

401、403、404 等不可恢复错误会立即降级，不进行无意义重试；429、5xx 和网络错误才会重试。

### Token 消耗异常

当前设计：

- 最多只分析最终前 10 项
- 前 10 项合并为一次模型请求
- 每项简介最多发送 240 个字符
- 只发送评分所需核心指标
- 模型只返回短摘要、商业分、机会等级和一条建议
- 单次批量输出硬上限为 700 Token

日志会显示实际 Token 使用量：

```text
AI 批量分析完成：项目=10 输入Token=... 输出Token=... 总Token=...
```

### 重复日报

CLI、API 与定时调度共用执行锁。同一时间已有任务运行时，新的执行会直接跳过。

## 日常维护

建议：

- 每天自动运行一次
- 定期备份 `./data/radar.db`
- 定期检查采集器失败日志
- 观察每轮实际 Token 使用量

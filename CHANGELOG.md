# 变更日志

## 当前稳定版本

### 已完成

- 多来源 AI 情报采集
- GitHub 近期 AI、LLM、AI Agent 项目发现
- Hacker News / Show HN 新项目发现
- Hugging Face 新模型发现
- arXiv 最新论文解析
- Product Hunt 近期 AI 产品采集
- 数据标准化与去重
- 新项目早期增长速度评分
- DeepSeek / OpenAI 兼容模型分析
- 最终前 10 项一次批量模型请求
- 模型输入字段压缩与简介截断
- 单次批量输出 700 Token 硬上限
- SQLite 持久化与数据库迁移
- 飞书全中文日报
- 命令行中文配置检查
- FastAPI 中文展示接口
- 定时任务与跨进程防重复执行
- Docker 部署与真实就绪检查
- 自动化回归测试
- GitHub Actions 持续集成

### 当前模型成本优化

```text
采集多个候选
    ↓
本地评分
    ↓
最终前 10 项
    ↓
压缩为必要字段
    ↓
一次 DeepSeek 批量请求
    ↓
每项短摘要 + 商业分 + 机会等级 + 一条建议
```

模型不再重复生成本地已经计算的热度分。

### 常用命令

```bash
docker exec ai-intelligence-radar python -m app.cli check
docker exec ai-intelligence-radar python -m app.cli
docker logs --tail 100 ai-intelligence-radar
```

### 当前范围

当前版本继续优先稳定：

- 新项目发现准确性
- 增长速度评分质量
- DeepSeek Token 成本
- 数据库存储可靠性
- 飞书通知质量
- Docker 与定时任务长期稳定性

在以上核心能力完成真实环境验收之前，不优先增加新的产品模块。

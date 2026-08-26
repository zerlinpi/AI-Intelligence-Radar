# AI 情报雷达稳定版本说明

## 版本定位

当前版本用于生产环境每日自动发现近期上线、正在快速升温的 AI 项目，并生成飞书中文情报。

## 已完成能力

- GitHub、Hacker News、Hugging Face、arXiv、Product Hunt 多源采集
- 近期项目筛选与数据去重
- 单位时间增长速度评分
- 最终前 10 项筛选
- DeepSeek / OpenAI 兼容模型中文分析
- 最终前 10 项一次批量模型调用
- DeepSeek 输入压缩与 700 Token 输出硬上限
- SQLite 历史数据持久化
- 飞书中文日报
- 中文命令行配置检查
- 中文 API 展示层
- APScheduler 每日自动运行
- CLI、API、定时任务防重复执行
- Docker 持久化部署
- 数据库自动迁移
- 自动化测试与 GitHub Actions 持续集成

## 生产更新

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose up -d --build
```

配置检查：

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

手动执行日报：

```bash
docker exec ai-intelligence-radar python -m app.cli
```

查看日志：

```bash
docker logs --tail 100 ai-intelligence-radar
```

## 当前重点

当前阶段不扩展新的产品模块，继续完成现有功能的真实环境验收与稳定性优化，重点关注：

- 新项目发现质量
- DeepSeek 实际 Token 消耗
- Product Hunt 真实数据
- SQLite 持久化
- 飞书通知完整性
- 定时任务长期稳定性

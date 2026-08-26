# AI 情报雷达

> 自动发现“刚上线、正在快速升温”的 AI 项目与产品。
>
> 系统采集公开数据，计算早期增长热度，对最终前 10 项使用一次 DeepSeek 批量中文分析，然后写入 SQLite 并推送飞书日报。

## 当前目标

本项目关注的是**新项目早期信号**，不是历史累计最热门项目。

```text
发现近期上线项目
        ↓
计算单位时间增长速度
        ↓
筛选早期热点前 10 项
        ↓
一次模型批量中文分析
        ↓
SQLite 持久化
        ↓
飞书中文日报
```

“新项目热度”强调上线后的增长速度，不等同于历史累计星标、热度票或下载量。

---

## 数据源

- **GitHub**：最近 7 天新建的 AI、LLM、AI Agent 项目，结合星标、分支和上线时间判断增长速度。
- **Hacker News / Show HN**：近期发布的 AI 项目，结合热度票、评论和发布时间判断早期热度。
- **Hugging Face**：最近 7 天新发布模型，结合下载、点赞和发布时间判断增长速度。
- **arXiv**：最新人工智能、机器学习、自然语言处理研究论文。
- **Product Hunt**：近期 AI 产品，结合热度票、评论和发布时间判断早期热度，需要 `PRODUCT_HUNT_TOKEN`。

品牌名、接口字段、环境变量名、URL 等技术标识保留官方写法；用户可见的日志、提示、接口说明和飞书内容统一使用中文。

---

## 早期热度评分

当前评分重点：

- 上线时间新鲜度
- 星标/天、热度票/天、下载/天等增长速度
- 分支、评论、点赞等早期互动
- 各数据源自身增长信号

系统先在本地完成评分，只对最终前 10 项调用模型。

---

## DeepSeek Token 优化

当前模型调用已经从“最多 10 个项目分别调用 10 次”改为：

```text
前 10 项
   ↓
压缩输入字段
   ↓
合并成 1 次批量请求
   ↓
一次返回 10 项短分析
```

具体限制：

- 每轮最多 **1 次批量模型请求**
- 每项标题最多发送 120 个字符
- 每项简介最多发送 240 个字符
- 只发送星标、分支、热度票、评论、下载、点赞、增长信号等必要指标
- 不再要求模型返回本地已经计算好的热度分
- 每项摘要不超过 45 字
- 每项建议不超过 25 字
- 每项只保留 1 条机会建议
- 单次批量输出硬上限 **700 Token**
- 即使旧 `.env` 仍写 `LLM_MAX_TOKENS=1200`，分析层也会限制到 700
- 401、403、404 等不可恢复错误立即降级，不进行无意义重试
- 429、5xx 和临时网络错误才会重试

日志会输出真实 Token 使用量：

```text
AI 批量分析完成：项目=10 输入Token=... 输出Token=... 总Token=...
```

DeepSeek 配置示例：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=700
```

---

## 飞书通知

配置：

```env
FEISHU_WEBHOOK=你的飞书机器人地址
```

日报主要包含：

- 项目名称与来源
- 大致上线时间
- 新项目热度
- 星标、热度票、下载等早期指标
- 单位时间增长速度
- 商业机会等级
- 商业分
- AI 中文判断
- 一条可关注机会
- 项目链接

示例结构：

```text
01｜项目名称

📍 来源：GitHub
🕒 约 8 小时前上线
🔥 新项目热度：84.6/100
📈 早期信号：星标 186 · 分支 14 · 星标增速约 558/天
💼 商业机会：高 · 82/100
🧠 AI 判断：……
💡 可关注机会：……
🔗 查看项目
```

---

## 环境变量

```bash
cp .env.example .env
```

核心配置：

```env
GITHUB_TOKEN=
PRODUCT_HUNT_TOKEN=

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=700

FEISHU_WEBHOOK=
DATABASE_URL=sqlite:///./data/radar.db

RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

说明：

- `GITHUB_TOKEN`：可选；不配置时 GitHub 接口频率限制更低。
- `PRODUCT_HUNT_TOKEN`：可选；不配置时会跳过 Product Hunt。
- `LLM_API_KEY`：模型分析必需。
- `FEISHU_WEBHOOK`：飞书推送必需。
- `DATABASE_URL`：Docker 默认使用 `./data/radar.db` 持久化。
- 调度器时区为 `Asia/Shanghai`（UTC+8）。

---

# Docker 部署

## 首次部署或更新

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose up -d --build
```

查看容器：

```bash
docker ps
```

API 默认只绑定服务器本机：

```text
127.0.0.1:8000->8000/tcp
```

不会默认向公网暴露执行接口。

---

## 配置检查

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

正常输出示例：

```text
[正常] 数据库
[正常] 飞书机器人地址
[正常] 模型密钥
[正常] 模型名称
[正常] 模型接口地址
[正常] GitHub 访问令牌
[提醒] Product Hunt 访问令牌
```

GitHub 和 Product Hunt 为可选数据源，因此未配置时显示“提醒”而不是主程序失败。

---

## 健康检查

```bash
curl http://localhost:8000/health
curl -i http://localhost:8000/ready
```

接口返回内容使用中文字段。

调度器正常时 `/ready` 返回 HTTP 200；未就绪时返回 HTTP 503。

---

## 手动运行日报

```bash
docker exec ai-intelligence-radar python -m app.cli
```

保存完整日志：

```bash
docker exec ai-intelligence-radar python -m app.cli 2>&1 | tee /root/radar-test.log
```

命令结束时只输出中文执行摘要，不再把完整内部字典打印到终端。

---

## 运行日志

```bash
docker logs --tail 100 ai-intelligence-radar
```

持续查看：

```bash
docker logs -f ai-intelligence-radar
```

正常流程会看到类似：

```text
日报开始执行：执行编号=...
采集器=GithubCollector 数量=... 耗时=...秒
采集器=HackerNewsCollector 数量=... 耗时=...秒
采集器=HuggingFaceCollector 数量=... 耗时=...秒
采集器=ArxivCollector 数量=... 耗时=...秒
采集器=ProductHuntCollector 数量=... 耗时=...秒
去重完成：采集=... 新项目=...
AI 批量分析完成：项目=... 输入Token=... 输出Token=... 总Token=...
数据库保存完成：数量=...
飞书通知发送成功
日报执行完成：...
```

---

## 数据库

Docker Compose 挂载：

```text
./data:/app/data
```

默认数据库：

```text
./data/radar.db
```

数据库保存来源项目真实发布时间，用于判断项目年龄和早期增长速度。

容器启动时会先执行数据库迁移，再启动服务。

---

## 接口

### `GET /health`

检查服务进程是否正常。

### `GET /ready`

检查调度器是否就绪。

- 就绪：HTTP 200
- 未就绪：HTTP 503

### `POST /run`

手动执行一次完整日报。返回内容使用中文字段。

---

## 定时任务

默认：

```text
每天 08:00
时区：Asia/Shanghai
```

配置：

```env
RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

非法时间值不会导致容器直接启动失败，会回退到默认值并输出中文警告。

CLI、API 与定时调度共用执行锁；已有任务运行时，第二次执行会直接跳过，避免重复调用模型、重复保存和重复发飞书。

---

## 测试

GitHub Actions 执行：

```bash
python -m pytest -v --tb=short
```

当前测试覆盖：

- DeepSeek / 兼容模型批量分析
- 单轮多个项目只发送一次模型请求
- 旧 1200 Token 配置仍被限制到 700
- 输入简介截断与无关指标过滤
- 模型异常降级
- 临时错误重试与不可恢复错误快速失败
- 数据清洗与去重
- 新项目热度评分
- SQLite 存储
- 来源发布时间持久化
- 飞书发送
- Product Hunt 近期 AI 产品过滤
- `/ready` 200 / 503
- 防止重复并发执行

---

## 当前阶段

当前继续优先稳定已有核心能力：

- 新项目发现准确性
- 增长速度评分质量
- DeepSeek 分析质量与 Token 成本
- 数据持久化可靠性
- 飞书日报可读性
- Docker 与定时任务长期稳定运行

核心链路完成真实环境验证之前，不优先增加仪表盘、趋势可视化等新模块。

---

## 许可证

MIT

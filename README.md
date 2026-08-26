# AI 情报雷达

> 自动发现正在快速升温的 AI 项目，并优先追踪 Amazon 政策、美国进口规则与产品合规审核变化。

系统采集公开数据，先在本地完成新鲜度、增长速度与商业优先级筛选，再使用一次 DeepSeek 批量分析，写入 SQLite，并推送中文飞书日报。

## 当前目标

本项目关注两类每日经营情报：

1. **美国跨境经营与合规变化**
   - Amazon 政策与审核
   - 美国 CBP 进口与清关规则
   - CPSC / FDA / FCC 产品合规要求
2. **早期 AI 产品机会**
   - 跨境电商直接相关项目优先
   - 可产品化为 SaaS、Agent、插件、API、自动化工具的项目优先
   - 重点看上线后的增长速度，而不是历史累计热度

当前主流程：

```text
采集 AI 项目 + 美国经营合规情报
        ↓
清洗 / 去重 / 近期过滤
        ↓
本地热度评分 + 跨境商业优先级
        ↓
最多 4 条政策 + 10 个项目
        ↓
一次 DeepSeek 批量深度分析
        ↓
SQLite 持久化
        ↓
飞书中文经营日报
```

---

## 数据源

### AI 项目

- **GitHub**：最近 7 天新建的 AI、LLM、AI Agent 项目，结合 Stars、Forks、上线时间判断增长速度。
- **Hacker News / Show HN**：近期 AI 项目，结合票数、评论和发布时间判断早期热度。
- **Hugging Face**：最近 7 天新发布模型，结合下载、点赞和发布时间判断增长速度。
- **arXiv**：最新人工智能、机器学习、自然语言处理研究论文。
- **Product Hunt**：近期 AI 产品，结合票数、评论和发布时间判断早期热度，需要 `PRODUCT_HUNT_TOKEN`。

Product Hunt 会同时保留产品 `tagline + description`，尽量给模型完整产品上下文。

### 美国跨境经营与合规

政策采集重点包括：

- **Amazon**：商品合规、Testing / Inspection / Certification、Listing 前置审核、Restricted Products、Account Health、高风险品类审核等。
- **CBP**：进口申报、关税、de minimis、电子申报、Importer of Record 等。
- **CPSC**：CPC / GCC、eFiling、第三方实验室测试、消费品安全要求等。
- **FDA**：食品、膳食补充剂、化妆品、医疗器械等品类的注册、列名与进口要求。
- **FCC**：Bluetooth、Wi-Fi、RF 设备的 Equipment Authorization 与相关市场准入要求。

政策采集优先限制在官方来源域名，并通过本地规则过滤普通营销内容。

---

## 早期热度与商业优先级

### 新项目热度

热度分主要衡量：

- 上线时间新鲜度
- Stars / 天、Votes / 天、Downloads / 天等单位时间增长速度
- Forks、评论、点赞等早期互动
- 各数据源自身 Momentum 信号

热度分仍然只代表**早期增长趋势**，不会因为项目品牌大或历史规模大额外加分。

### 商业优先级

在热度分之外，系统额外判断：

- 是否直接服务 Amazon、Shopify、TikTok Shop、独立站等跨境场景
- 是否涉及 Listing、SEO、广告、本地化、客服、选品、竞品、定价、物流、库存、评论、达人营销等
- 是否具备 SaaS、Agent、插件、API、自动化工作流等产品化形态

最终项目选择使用：

```text
selection_score = trend_score + priority_score
```

但飞书中的“早期热度”仍保持纯趋势含义。

---

## DeepSeek 深度分析

### 当前模型策略

日报属于**离线经营分析任务**，不追求秒级响应，因此当前策略优先保证分析完整度：

```text
deepseek-v4-pro
+
Thinking = enabled
+
reasoning_effort = max
+
内部 SSE 流式接收，避免长时间空闲连接被中间网络切断
+
单次请求最长等待 = 900 秒（默认 15 分钟）
+
输出上限 = 65536 Token
```

一次批量最多分析：

```text
4 条政策 + 10 个项目 = 14 条
```

DeepSeek Thinking 模式的推理 Token 与最终可见正文共同占用 completion 预算。实际单项测试已经出现 2K+ completion Token，因此 8192 对 14 条批量分析过紧；当前预留 65536 Token，仍然只是上限，实际计费按模型真实生成量计算。

主批量请求默认只执行一次。因为单次请求已经允许最长 15 分钟，超时后不会自动把整批任务再次重复执行。

如果模型已经成功响应，但发生以下情况，系统才会进行针对性恢复：

- JSON Output 偶发为空
- 返回结果缺少某个序号
- 部分项目没有完整结构化结果

缺少个别条目时只重试缺失条目，不重复分析已经成功的内容。

### JSON 输出

模型使用结构化 JSON 输出：

```json
{
  "结果": [
    [1, "用途", "判断", 90, "高", "建议"]
  ]
}
```

系统会记录：

- 输入 Token
- 输出 Token
- 其中推理 Token
- 推算的最终正文 Token
- 总 Token
- 是否有降级条目
- `finish_reason`

日志示例：

```text
AI 批量分析完成：条目=14 降级=0 输入Token=... 输出Token=... 其中推理Token=... 正文Token=... 总Token=... 结束原因=stop
```

### AI 失败时的处理

模型失败不会再只显示：

```text
项目用途暂无法生成，请查看项目原始说明。
```

当前降级策略会优先展示数据源原始 description，并明确标记本条 AI 深度分析未完成。

更重要的是：**AI fallback 不会被数据库当成永久成功记录。**

```text
AI 成功
→ 保存
→ 下次正常 URL 去重

AI 失败
→ 可降级发送飞书
→ 不视为已成功处理
→ 后续采集到同一 URL 时再次分析

历史 fallback
→ 重新分析
→ 成功后原地覆盖旧记录
```

这样一次模型超时不会永久丢失该项目或政策。

---

## DeepSeek 配置

推荐：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=65536
LLM_TIMEOUT_SECONDS=900
```

说明：

- `LLM_MAX_TOKENS=65536` 是 completion 输出上限，包含 Thinking 模式中的推理 Token 与最终正文 Token，不代表每次固定消耗 65536 Token。
- `LLM_TIMEOUT_SECONDS=900` 表示单次模型请求最多等待 15 分钟。
- DeepSeek Thinking 模式下不依赖 `LLM_TEMPERATURE` 控制推理质量；该变量主要保留给其他兼容模型。
- DeepSeek 使用内部 SSE 流式接收，但飞书仍然只在完整 JSON 汇总完成后一次发送最终日报。
- 401、403、404、422 等不可恢复错误立即失败，不做无意义重试。
- 429、5xx、网络问题属于可恢复错误；但主批量长任务默认只请求一次，避免 15 分钟超时后再次整批重复等待。

---

## 飞书日报

日报信息架构：

```text
美国跨境经营雷达

01 今日合规重点
   ├ Amazon 政策与审核
   ├ 美国跨境进口新规
   └ 美国市场产品审核

02 跨境电商直接相关项目
   ├ 产品描述
   ├ 增长信号
   ├ 价值判断
   └ 可借鉴方向

03 其他可产品化 AI 项目
   ├ 产品描述
   ├ 增长信号
   ├ 价值判断
   └ 可借鉴方向
```

项目条目示例：

```text
01｜项目名称  查看项目 →
GitHub · 8小时前  🔥 87  💼 92 · 高
🎯 跨境电商 · 可产品化
产品描述：...
增长信号：...
价值判断：...
可借鉴方向：...
```

政策条目根据类别使用不同字段：

```text
Amazon：核心变化 / 卖家影响 / 建议动作
CBP：新规要点 / 进口影响 / 建议动作
CPSC/FDA/FCC：审核要求 / 影响产品或风险 / 准备资料
```

---

## 环境变量

首次配置：

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
LLM_MODEL=deepseek-v4-pro
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=65536
LLM_TIMEOUT_SECONDS=900

FEISHU_WEBHOOK=
DATABASE_URL=sqlite:///./data/radar.db

RADAR_RUN_HOUR=8
RADAR_RUN_MINUTE=0
```

说明：

- `GITHUB_TOKEN`：可选；不配置时 GitHub API 频率限制更低。
- `PRODUCT_HUNT_TOKEN`：可选；不配置时自动跳过 Product Hunt。
- `LLM_API_KEY`：模型分析必需。
- `FEISHU_WEBHOOK`：飞书推送必需。
- `DATABASE_URL`：Docker 默认使用 `./data/radar.db` 持久化。
- 调度器时区为 `Asia/Shanghai`（UTC+8）。

品牌名、接口字段、环境变量、URL 等官方技术标识保留官方写法；用户可见日志、提示和飞书内容使用中文。

---

# Docker 部署

## 首次部署或更新

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose up -d --build
```

API 默认只绑定服务器本机：

```text
127.0.0.1:8000->8000/tcp
```

不会默认向公网暴露执行接口。

不要使用会影响服务器其他容器的全局 Docker 清理命令。

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

确认模型运行参数：

```bash
docker exec -i ai-intelligence-radar python - <<'PY'
from app.config import LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS

print("模型提供方:", LLM_PROVIDER)
print("模型:", LLM_MODEL)
print("输出Token上限:", LLM_MAX_TOKENS)
print("单次请求最长等待:", LLM_TIMEOUT_SECONDS, "秒")
PY
```

---

## 健康检查

```bash
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

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

由于 DeepSeek 使用长时 Thinking，AI 阶段可能持续数分钟。内部会持续接收 SSE 流，最终飞书仍然只发送完整日报。

---

## 运行日志

查看最近日志：

```bash
docker logs --tail 100 ai-intelligence-radar
```

持续查看：

```bash
docker logs -f ai-intelligence-radar
```

正常流程类似：

```text
日报开始执行：执行编号=...
采集器=GithubCollector 数量=... 耗时=...秒
采集器=HackerNewsCollector 数量=... 耗时=...秒
采集器=HuggingFaceCollector 数量=... 耗时=...秒
采集器=ArxivCollector 数量=... 耗时=...秒
采集器=ProductHuntCollector 数量=... 耗时=...秒
政策采集：数量=... 耗时=...秒
去重完成：项目=... 新项目=... 政策=... 新政策=...
DeepSeek 流式连接已建立，正在等待完整分析结果
模型流式响应完成：数据块=... 思考字符=... 正文字符=... 结束原因=stop
AI 批量分析完成：条目=14 降级=0 输入Token=... 输出Token=... 其中推理Token=... 正文Token=... 总Token=... 结束原因=stop
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

数据库保存来源真实发布时间，用于判断项目年龄和早期增长速度。

对于历史 AI fallback 记录：

- 去重检查不会把它们视为已成功完成
- 后续会重新进入模型分析
- 分析成功后会覆盖旧 fallback 记录

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

生产环境不要把 `/run` 直接暴露到公网。

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

CLI、API 与定时调度共用执行锁；已有任务运行时，第二次执行会直接跳过，避免重复调用模型、重复保存和重复发飞书。

---

## 测试

GitHub Actions 执行：

```bash
python -m pytest -v --tb=short
```

当前测试重点覆盖：

- DeepSeek / OpenAI 兼容模型批量分析
- DeepSeek JSON Output
- DeepSeek Thinking `enabled` + `reasoning_effort=max`
- DeepSeek SSE 长任务流式聚合
- 65536 Token 输出上限
- 推理 Token 与正文 Token 拆分统计
- 长任务超时配置
- 模型返回缺失条目的定向恢复
- 模型异常 fallback
- fallback 记录自动重试与成功后覆盖
- 临时错误重试与不可恢复错误快速失败
- 数据清洗、URL 去重、早期热度评分
- SQLite 持久化
- 来源发布时间持久化
- 飞书报告结构
- Product Hunt 近期 AI 产品过滤与完整说明保留
- `/ready` 200 / 503
- 防止重复并发执行

---

## 当前阶段

当前继续优先稳定已有核心能力：

- 美国跨境政策与合规采集准确性
- 新项目发现准确性
- 早期增长速度评分质量
- DeepSeek 分析完整度与稳定性
- fallback 自动恢复
- 数据持久化可靠性
- 飞书日报决策价值
- Docker 与定时任务长期稳定运行

在核心链路完成真实环境验证之前，不优先增加仪表盘、趋势可视化等无关模块。

---

## 许可证

MIT
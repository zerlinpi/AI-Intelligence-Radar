# AI 情报雷达

> 自动发现正在快速升温的 AI 项目，并优先追踪 Amazon 政策、美国进口规则与产品合规审核变化。

系统采集公开数据，先在本地完成新鲜度、增长速度与商业优先级筛选，再使用 DeepSeek V4 Pro 批量分析，写入 SQLite，并转换为结构化 Decision Model，最终通过飞书发送经营决策日报。

## 当前目标

每日重点关注：

1. **美国跨境经营与合规变化**
   - Amazon 政策与审核
   - 美国 CBP 进口与清关规则
   - CPSC / FDA / FCC 产品合规要求
2. **早期 AI 产品机会**
   - 跨境电商直接相关项目优先
   - SaaS、Agent、插件、API、自动化产品机会优先
   - 重点看上线后的增长速度，而不是历史累计规模

主流程：

```text
采集 AI 项目 + 美国经营合规情报
        ↓
清洗 / 去重 / 近期过滤
        ↓
本地热度评分 + 跨境商业优先级
        ↓
最多 4 条政策 + 10 个项目
        ↓
DeepSeek V4 Pro max thinking 批量分析
        ↓
SQLite 保存完整分析
        ↓
ReportDecisionModel
        ↓
结构化 Card Builder
        ↓
3 个逻辑板块
        ↓
按 Payload 自动分页为 N 张飞书卡
```

---

## 数据源

### AI 项目

- GitHub：近期 AI / LLM / Agent 项目，结合 Stars、Forks、上线时间判断早期增速。
- Hacker News / Show HN：结合票数、评论和发布时间判断早期热度。
- Hugging Face：近期新模型，结合下载、点赞和发布时间判断增长速度。
- arXiv：AI、ML、NLP 最新研究。
- Product Hunt：近期 AI 产品，需要 `PRODUCT_HUNT_TOKEN`；同时保留 tagline + description。

### 美国跨境经营与合规

- Amazon：商品合规、Testing / Inspection / Certification、Listing 前置审核、Restricted Products、Account Health 等。
- CBP：进口申报、关税、de minimis、电子申报、Importer of Record 等。
- CPSC：CPC / GCC、eFiling、第三方测试与消费品安全要求。
- FDA：食品、膳食补充剂、化妆品、医疗器械等注册、列名与进口要求。
- FCC：Bluetooth、Wi-Fi、RF 设备 Equipment Authorization。

政策采集优先限制在官方来源域名。

---

# DeepSeek 深度分析

当前生产策略：

```text
deepseek-v4-pro
+
Thinking = enabled
+
reasoning_effort = max
+
SSE 流式接收
+
默认 completion 上限 = 131072 Token
+
程序硬上限 = 384000 Token
+
单次请求最长等待 = 900 秒
```

DeepSeek V4 Pro 当前官方规格为 1M context、最大输出 384K。项目默认不直接使用 384K，而是使用 131072 作为日报常规预算，在完整度、成本和异常输出风险之间保留余量。

`LLM_MAX_TOKENS` 是最大生成预算，不代表每次固定消耗。日志会分别记录：

- 输入 Token
- completion Token
- reasoning Token
- 最终正文 Token
- total Token
- finish_reason
- fallback 数量

示例：

```text
AI 批量分析完成：条目=14 降级=0 输入Token=... 输出Token=... 其中推理Token=... 正文Token=... 总Token=... 结束原因=stop
```

### 推荐配置

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=131072
LLM_TIMEOUT_SECONDS=900
```

如果实际长期出现 `finish_reason=length`，可以继续提高 `LLM_MAX_TOKENS`，程序允许最高 `384000`。

AI fallback 不会被数据库视为永久成功；后续重新采集时会再次分析，成功后覆盖旧 fallback。

---

# 飞书日报

日报保持三个**逻辑板块**，但不再强制只有三张物理卡：

```text
① 决策摘要
② 美国合规雷达
③ 产品机会雷达
```

任何板块超过单卡 Payload 预算时自动分页：

```text
美国合规雷达｜1/2
美国合规雷达｜2/2

产品机会雷达｜1/3
产品机会雷达｜2/3
产品机会雷达｜3/3
```

## 核心原则：完整文案，不硬截断

生产 Card Builder **不再对业务文案设置字符绝对上限**。

以下字段全部保留模型完整内容：

- 今日判断
- Top Actions
- 政策核心变化
- 卖家影响
- 新规要点
- 进口影响
- 审核要求
- 影响产品
- 风险
- 准备资料
- 下一步
- 产品描述
- 增长信号
- 价值判断
- 可借鉴方向

当内容过长时：

```text
完整正文
→ 计算真实 UTF-8 Payload
→ 优先在句号/分号/逗号等自然边界拆分
→ 自动增加物理卡片
→ 不删除字符
```

`FEISHU_PROJECTS_PER_CARD=5` 现在表示产品机会页优先每页放 5 个项目，不是“只显示前 5 个”。后续项目继续分页发送。

---

## 飞书视觉语义

### 1. 决策摘要

Header：`turquoise`

```text
🧭 今日判断        ← grey 决策块
📊 今日概览
① 必须             ← grey
② 关注             ← grey
③ 研究             ← grey
```

Top Actions 仍固定最多 3 条，这是信息架构限制，不是文本长度限制。

### 2. 美国合规雷达

Header 根据当天最高风险动态变化：

```text
存在高风险 → red
最高中风险 → orange
仅低风险/无风险 → turquoise
```

颜色只做视觉辅助，正文仍明确显示：

```text
🔴 高风险
🟠 中风险
🟢 低风险
```

美国市场产品审核按决策顺序展示：

```text
📌 审核要求
🎯 影响产品        ← grey
⚠️ 风险            ← grey
📋 准备资料        ← grey
✅ 下一步           ← grey
[查看官方原文]      ← 独立按钮
```

Amazon / CBP 政策也会独立显示核心变化、经营影响、下一步和官方原文按钮。

### 3. 产品机会雷达

Header：`blue`

单项目结构：

```text
项目名
来源 · 时间 · 热度 · 商业分
标签

🧩 做什么
📈 增长信号
🧠 价值判断        ← grey
🛠️ 可借鉴方向      ← grey
[查看项目]          ← 独立按钮
```

这样产品机会与红/橙色合规风险在视觉上不会混淆。

---

## Payload 与可靠性

飞书自定义机器人单请求仍按 18 KiB 项目软预算控制：

```env
FEISHU_MAX_PAYLOAD_BYTES=18432
FEISHU_PROJECTS_PER_CARD=5
FEISHU_MAX_RETRIES=3
FEISHU_SEND_TIMEOUT_SECONDS=10
FEISHU_OUTBOX_DIR=./data/feishu-outbox
```

完整内容通过分页控制 Payload，而不是截断。

发送前按真实 UTF-8 JSON bytes 校验。卡片发送使用持久化 Outbox：

```text
生成卡片
→ 写入 ./data/feishu-outbox
→ 顺序发送
→ 每张成功后记录状态
→ 全部完成后删除队列文件
```

容器或进程中途重启后会继续补发未完成卡片。损坏队列会被隔离到 bad 目录。

网络 timeout / connection error、HTTP 429 / 5xx 会重试；不可恢复 4xx 快速失败。Interactive Card 无法发送时会降级为 plain text。

---

# 数据库与运行稳定性

默认：

```env
DATABASE_URL=sqlite:///./data/radar.db
```

Docker 挂载：

```text
./data:/app/data
```

SQLite 文件模式启用：

```text
WAL
busy_timeout = 15000 ms
pool_pre_ping
PRAGMA quick_check
```

CLI / API / Scheduler 共用跨进程执行锁，避免重复日报并发运行。

日报状态：

```text
success  完整成功
partial  已生成但存在 fallback / 保存不完整 / 飞书待补发
failed   关键预检或执行阶段失败
skipped  已有任务运行，本轮跳过
```

---

# Docker 部署

首次部署或更新：

```bash
cd /opt/AI-Intelligence-Radar
git pull
docker compose build --no-cache radar
docker compose up -d --force-recreate radar
```

API 默认只绑定：

```text
127.0.0.1:8000
```

不要使用会影响服务器其他容器的全局 Docker 清理命令。

### 配置检查

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

### 健康检查

```bash
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

### 手动运行一次日报

```bash
docker exec ai-intelligence-radar python -m app.cli
```

保存日志：

```bash
docker exec ai-intelligence-radar python -m app.cli 2>&1 | tee /root/radar-test.log
```

由于 DeepSeek 使用 max thinking，AI 阶段可能持续数分钟。

---

# 定时任务

默认：

```text
每天 08:00
REPORT_TIMEZONE=Asia/Shanghai
```

---

# CI

GitHub Actions 会执行：

```text
依赖完整性检查
Python compileall
Docker Compose 校验
生产 Preflight Smoke Test
pytest
```

重点覆盖：

- DeepSeek JSON Output / Thinking / SSE
- 131072 默认输出预算与 384000 硬上限
- 缺失条目恢复和 fallback
- SQLite 持久化与 WAL
- Product Hunt / policy collectors
- ReportDecisionModel
- 飞书完整文案无损分页
- 动态 Header 视觉语义
- 外链按钮
- Payload 安全预算
- Outbox 断点补发
- 429 / 5xx 重试与 4xx 快速失败
- readiness / preflight
- 跨进程防重复执行

---

## 许可证

MIT

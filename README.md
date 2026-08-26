# AI 情报雷达

> 自动发现正在快速升温的 AI 项目，并优先追踪 Amazon 政策、美国进口规则与产品合规审核变化。

系统采集公开数据，先在本地完成新鲜度、增长速度与商业优先级筛选，再使用一次 DeepSeek 批量分析，写入 SQLite，并将结果转换为结构化 Decision Model，最终推送 3 张中文飞书决策卡。

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
SQLite 保存完整分析
        ↓
Report Decision Model
        ↓
结构化 Card Builder
        ↓
3 张飞书决策卡
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

热度分只代表**早期增长趋势**，不会因为项目品牌大或历史规模大额外加分。

### 商业优先级

在热度分之外，系统额外判断：

- 是否直接服务 Amazon、Shopify、TikTok Shop、独立站等跨境场景
- 是否涉及 Listing、SEO、广告、本地化、客服、选品、竞品、定价、物流、库存、评论、达人营销等
- 是否具备 SaaS、Agent、插件、API、自动化工作流等产品化形态

最终项目选择使用：

```text
selection_score = trend_score + priority_score
```

飞书中的“早期热度”仍保持纯趋势含义。

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
内部 SSE 流式接收
+
单次请求最长等待 = 900 秒（默认 15 分钟）
+
输出上限 = 65536 Token
```

一次批量最多分析：

```text
4 条政策 + 10 个项目 = 14 条
```

DeepSeek Thinking 模式的推理 Token 与最终可见正文共同占用 completion 预算。65536 Token 是输出上限，不代表每次固定消耗，实际仍按真实生成量计算。

主批量请求默认只执行一次。若模型已经成功响应，但出现 JSON 为空或个别序号缺失，系统才做针对性恢复；缺少个别条目时只重试缺失条目，不重复分析已成功内容。

### JSON 输出

模型使用结构化 JSON。政策中的美国市场产品审核额外拆出“影响产品 / 风险 / 准备资料”：

```json
{
  "结果": [
    [
      1,
      "用途或审核要求",
      "判断",
      90,
      "高",
      "建议",
      "影响产品",
      "风险",
      "准备资料"
    ]
  ]
}
```

非产品合规审核条目的最后三个字段返回空字符串。

系统记录：

- 输入 Token
- 输出 Token
- 推理 Token
- 最终正文 Token
- 总 Token
- 是否存在降级条目
- `finish_reason`

日志示例：

```text
AI 批量分析完成：条目=14 降级=0 输入Token=... 输出Token=... 其中推理Token=... 正文Token=... 总Token=... 结束原因=stop
```

### AI 失败时的处理

AI fallback 不会被数据库当作永久成功记录：

```text
AI 成功
→ 保存
→ 下次正常 URL 去重

AI 失败
→ 可使用原始说明降级展示
→ 不视为已成功处理
→ 后续再次分析

历史 fallback
→ 重新分析
→ 成功后覆盖旧 fallback
```

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

- `LLM_MAX_TOKENS=65536` 是 completion 上限，不是固定消耗。
- `LLM_TIMEOUT_SECONDS=900` 表示单次模型请求最多等待 15 分钟。
- DeepSeek 使用内部 SSE 接收，但飞书只在完整分析完成后批量发送。
- 401、403、404、422 等不可恢复错误立即失败。
- 429、5xx、网络问题属于可恢复错误。

---

# 飞书三卡日报

生产日报已经从“一个长 Markdown 卡片”升级为固定的**三张结构化决策卡**。

```text
① 决策摘要卡
   ├ 今日判断
   ├ ① 必须
   ├ ② 关注
   └ ③ 研究

② 合规雷达卡
   ├ Amazon 政策与审核
   ├ 美国跨境进口新规
   └ 美国市场产品审核

③ 产品机会卡
   ├ 跨境电商直接相关
   └ 其他可产品化信号
```

## 1. 决策摘要卡

目标：打开飞书后 5 秒内回答“今天有没有必须处理的事情”。

- Header：`turquoise`
- 今日判断：约 60 字以内
- Top Actions：固定最多 3 条
- ① 必须 / ② 关注 / ③ 研究：纵向 `grey` 决策块
- 布局：1:4 标签 / 正文两列

示意：

```text
美国跨境经营雷达｜08月26日

今日判断
发现 1 项高风险合规变化，先处理 CPSC 准入资料。

合规 4 · 高风险 1 · 新项目 10 · 重点机会 3

① 必须 | 核对 CPC/GCC 与 eFiling 字段
② 关注 | 检查 RF 产品 FCC 授权资料
③ 研究 | 评估 Listing + 合规检查产品方向
```

## 2. 合规雷达卡

政策分成三组：

```text
A｜Amazon 政策与审核
B｜美国跨境进口新规
C｜美国市场产品审核
```

其中产品审核固定按决策顺序展示：

```text
审核要求
🎯 影响产品   ← grey
⚠️ 风险       ← grey
📋 准备资料   ← grey
✅ 下一步      ← white
官方原文 →
```

不会用大片红色背景表示普通日报风险。风险状态同时使用文字和 Emoji：

```text
🔴 高风险
🟠 中风险
🟢 低风险
```

## 3. 产品机会卡

产品区保持“少设计”：

```text
标题
来源 · 时间 · 热度 · 商业分
最多 3 个标签
一句产品描述
增长信号
一句判断
一句产品方向
查看项目 →
```

默认只在卡片中展示优先级最高的 **5 个项目**；其余候选仍进入数据库，不在飞书卡片中堆积。这样同时优化移动端扫读和 Webhook Payload 大小。

## 展示预算

DeepSeek 保留完整分析，飞书 Renderer 单独压缩展示：

| 字段 | 展示上限 |
| --- | ---: |
| 今日判断 | 60 |
| Top Action | 52 |
| 审核要求 | 72 |
| 影响产品 | 48 |
| 风险 | 56 |
| 准备资料 | 64 |
| 下一步 | 46 |
| 产品标题 | 32 |
| 产品描述 | 72 |
| 价值判断 | 64 |
| 产品方向 | 52 |

压缩优先保留完整句和完整分句，最后才使用硬截断。

## 结构化 Card Builder

生产链路不再使用：

```text
RadarItem
→ 拼 Markdown
→ feishu.py 用 Regex 猜字段
→ 卡片 JSON
```

现在使用：

```text
RadarItem + Analysis
→ ReportDecisionModel
→ app/cards/builders.py
→ CardEnvelope
→ app/feishu.py
→ 飞书 Webhook
```

目录：

```text
app/cards/
├── __init__.py
├── models.py      # Decision Model
├── builders.py    # 3 张卡片 Builder
├── styles.py      # 视觉语义与展示预算
└── text.py        # 语义压缩 / Display Width / UTF-8 字节计算
```

旧 Markdown / Regex 路径只保留兼容接口，不参与正式日报发送。

## Payload 与降级

当前仍使用飞书自定义机器人 Webhook。项目按 **18 KiB** 软预算控制单张请求体，为官方 20 KB 边界预留安全空间。

正式发送前按真实 UTF-8 JSON 字节数计算：

```python
len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
```

发送策略：

```text
正常 Card Payload ≤ 18 KiB
→ 发送 Interactive Card

Payload > 18 KiB
→ 不硬发
→ 直接发送 Plain-text fallback

卡片结构/业务发送失败
→ 尝试 Plain-text fallback
```

HTTP 行为：

- 网络 timeout / connection error：指数退避 + jitter
- HTTP 429 / 5xx：重试
- HTTP 400 等不可重试 4xx：立即停止，不盲目重复发送
- 飞书业务 code 非 0：记录错误并走 fallback

---

## 飞书配置

```env
FEISHU_WEBHOOK=

# 项目软预算；飞书自定义机器人官方硬边界仍为 20 KB
FEISHU_MAX_PAYLOAD_BYTES=18432

# 产品机会卡最多展示 5 项
FEISHU_PROJECTS_PER_CARD=5

FEISHU_MAX_RETRIES=3
FEISHU_SEND_TIMEOUT_SECONDS=10

REPORT_LOCALE=zh-CN
REPORT_TIMEZONE=Asia/Shanghai
```

这些配置已有默认值；升级现有服务器时不强制修改 `.env`。

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
FEISHU_MAX_PAYLOAD_BYTES=18432
FEISHU_PROJECTS_PER_CARD=5
FEISHU_MAX_RETRIES=3
FEISHU_SEND_TIMEOUT_SECONDS=10
REPORT_LOCALE=zh-CN
REPORT_TIMEZONE=Asia/Shanghai

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
- `REPORT_TIMEZONE` 控制日报日期显示；调度器当前仍按 `Asia/Shanghai` 运行。

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

不要使用会影响服务器其他容器的全局 Docker 清理命令。

---

## 配置检查

```bash
docker exec ai-intelligence-radar python -m app.cli check
```

GitHub 和 Product Hunt 为可选数据源，因此未配置时显示“提醒”而不是主程序失败。

确认核心运行参数：

```bash
docker exec -i ai-intelligence-radar python - <<'PY'
from app.config import (
    LLM_MODEL,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT_SECONDS,
    FEISHU_MAX_PAYLOAD_BYTES,
    FEISHU_PROJECTS_PER_CARD,
)

print("模型:", LLM_MODEL)
print("输出Token上限:", LLM_MAX_TOKENS)
print("单次请求最长等待:", LLM_TIMEOUT_SECONDS, "秒")
print("飞书单卡软预算:", FEISHU_MAX_PAYLOAD_BYTES, "字节")
print("产品卡展示上限:", FEISHU_PROJECTS_PER_CARD)
PY
```

---

## 健康检查

```bash
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

---

## 手动运行日报

```bash
docker exec ai-intelligence-radar python -m app.cli
```

保存完整日志：

```bash
docker exec ai-intelligence-radar python -m app.cli 2>&1 | tee /root/radar-test.log
```

由于 DeepSeek 使用长时 Thinking，AI 阶段可能持续数分钟；飞书只在完整分析完成后批量发送最终 3 张日报卡片。

正常发送日志类似：

```text
飞书卡片发送成功：类型=summary Payload=...字节
飞书卡片发送成功：类型=compliance Payload=...字节
飞书卡片发送成功：类型=products Payload=...字节
飞书日报发送成功：执行编号=... 卡片=3
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

对于历史 AI fallback 记录：

- 去重检查不会把它们视为已成功完成
- 后续会重新进入模型分析
- 分析成功后会覆盖旧 fallback 记录

---

## 接口

### `GET /health`

检查服务进程是否正常。

### `GET /ready`

检查调度器是否就绪。

### `POST /run`

手动执行一次完整日报。生产环境不要把 `/run` 直接暴露到公网。

---

## 定时任务

默认：

```text
每天 08:00
时区：Asia/Shanghai
```

CLI、API 与定时调度共用执行锁；已有任务运行时，第二次执行会直接跳过。

---

## 测试

GitHub Actions 执行：

```bash
python -m pytest -v --tb=short
```

当前测试重点覆盖：

- DeepSeek JSON Output / Thinking / SSE 长任务
- 65536 Token 输出上限与 Token 统计
- 缺失条目定向恢复与 fallback 自动重试
- 数据清洗、URL 去重、评分、SQLite 持久化
- Product Hunt 近期项目过滤
- `ReportDecisionModel`
- 固定 3 张飞书日报卡
- Top Actions 最多 3 条
- 产品机会卡最多 5 项
- 产品审核的影响产品 / 风险 / 准备资料灰底决策块
- 单卡 18 KiB 安全预算
- 超限和卡片失败时 Plain-text fallback
- 429 / 5xx 重试与 4xx 快速失败
- `/ready` 200 / 503
- 防止重复并发执行

---

## 当前阶段

继续优先稳定已有核心能力：

- 美国跨境政策与合规采集准确性
- 新项目发现与早期增长评分质量
- DeepSeek 分析完整度与稳定性
- 结构化三卡飞书日报的决策价值
- Payload 与降级发送可靠性
- Docker 与定时任务长期稳定运行

真正需要卡片原地更新、确认按钮或动态状态时，再考虑迁移企业应用 + CardKit / Card JSON 2.0；当前日报继续使用稳定的 Webhook 批量发送路线。

---

## 许可证

MIT
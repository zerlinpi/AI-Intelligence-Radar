# GitHub Actions 无服务器日报设计

日期：2026-09-07

## 1. 目标

把 AI-Intelligence-Radar 从“长期服务器进程 + APScheduler”运行方式扩展为“GitHub Actions 每日无服务器运行”，同时保持现有业务逻辑、AI 分析逻辑、筛选规则、SQLite 历史、飞书卡片结构与视觉语义不变。

最终目标：

```text
GitHub Actions 每天北京时间 08:00 触发
        ↓
恢复上一次 data/ 运行状态
        ↓
安装项目依赖并执行现有 CLI
        ↓
GitHub / Hacker News / Hugging Face / arXiv / Product Hunt
+ Amazon / CBP / CPSC / FDA / FCC
        ↓
沿用现有清洗、去重、热度与商业优先级评分
        ↓
沿用现有 DeepSeek 批量深度分析
        ↓
沿用现有 SQLite / ReportDecisionModel / Card Builder
        ↓
沿用现有飞书 3 个逻辑板块与自动分页
        ↓
保存 data/ 状态 + Actions 状态摘要 + Artifact 备份
```

## 2. 非目标

本次不重写采集器、不在 GitHub Actions YAML 中复制业务评分规则、不改变 DeepSeek Prompt、不重做飞书消息模板，也不引入新的数据库服务。

`app.pipeline.run_daily_radar()` 继续作为唯一生产日报业务入口。

## 3. 调度

新增独立生产 Workflow：

```text
.github/workflows/daily-radar.yml
```

触发方式：

- `schedule`: `0 0 * * *`
- `workflow_dispatch`: 支持手动立即运行

GitHub Actions Cron 使用 UTC，因此 `00:00 UTC` 对应 `Asia/Shanghai 08:00`。

Workflow 设置并发组：

```text
concurrency:
  group: ai-intelligence-radar-daily
  cancel-in-progress: false
```

同一时刻只允许一个生产日报运行，避免手动触发与定时触发重叠。

仓库现有 `app/scheduler.py` 保留，作为 Docker/VPS 部署兼容路径；GitHub Actions 不启动常驻 Web 服务，因此不会触发 APScheduler。无需删除旧部署能力。

## 4. 业务执行路径

Actions 不调用新的分析脚本，而是直接执行：

```bash
python -m app.cli run
```

CLI 内部继续调用：

```text
run_daily_radar()
→ execution_lock
→ preflight
→ collect_sources / collect_policies
→ normalize / recent filter / scoring / dedupe
→ DeepSeek analyze_items
→ SQLite save
→ ReportDecisionModel
→ build_daily_cards
→ send_feishu_cards
→ record_run_safe
```

因此生产逻辑只有一份，不存在“服务器版”和“Actions 版”结果漂移。

## 5. 数据源保持不变

AI 产品与技术平台：

- GitHub
- Hacker News / Show HN
- Hugging Face
- arXiv
- Product Hunt

美国跨境经营与产品合规：

- Amazon
- CBP
- CPSC
- FDA
- FCC

现有 `MAX_REPORT_ITEMS=10`、`MAX_POLICY_ITEMS=4`、最近 14 天筛选、每来源配额、商业分阈值和去同质化规则全部保持不变。

## 6. 飞书输出保持不变

正常运行时仍完全使用现有：

```text
ReportDecisionModel
→ app.cards.build_daily_cards
→ app.feishu.send_feishu_cards
```

逻辑板块保持：

1. 决策摘要
2. 美国合规雷达
3. 产品机会雷达

保持现有 Header 颜色、风险语义、灰色重点块、官方原文按钮、项目按钮、18 KiB 软 Payload 预算、自动分页、Outbox、429/5xx 重试与 plain text fallback。

GitHub Actions 不重新拼装正常日报消息。

## 7. 状态持久化

GitHub-hosted Runner 是临时环境，因此必须在每日运行之间恢复 `data/`。

需要持久化的内容包括：

```text
data/radar.db
data/radar.db-wal
data/radar.db-shm
data/run-history.json
data/feishu-outbox/
data/backups/
```

采用两层策略：

### 7.1 主路径：GitHub Actions Cache

运行开始：

- 使用 `actions/cache/restore` 恢复最新 `radar-state-*` Cache。
- 没有历史 Cache 时创建空 `data/`，作为首次运行。

运行结束：

- 无论日报成功或失败，都执行 `actions/cache/save`。
- Cache Key 带 `github.run_id`，避免 GitHub Cache 不可覆盖的问题。
- `restore-keys` 使用稳定前缀，让下一次运行恢复最新状态。

这样 SQLite 历史、重复过滤、运行历史和未完成飞书 Outbox 都可跨 Runner 延续。

### 7.2 备份路径：Workflow Artifact

每次运行结束用 `actions/upload-artifact` 上传 `data/` 快照：

```text
artifact name: radar-state-<run_id>
```

Artifact 用于人工恢复和故障审计，不作为正常运行的唯一恢复机制。

保留期建议 30 天。

## 8. Secrets 与环境变量

生产 Workflow 只从 GitHub Secrets 读取敏感信息。

必需：

```text
LLM_API_KEY
FEISHU_WEBHOOK
```

按当前生产配置使用：

```text
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=131072
LLM_TIMEOUT_SECONDS=900
REPORT_TIMEZONE=Asia/Shanghai
DATABASE_URL=sqlite:///./data/radar.db
```

可选：

```text
PRODUCT_HUNT_TOKEN
```

GitHub 数据源优先使用 Actions 自动提供的：

```text
GITHUB_TOKEN=${{ github.token }}
```

任何 Webhook、API Key 或 Token 都不得写入仓库文件、Actions 日志或 Artifact。

## 9. GitHub Actions 状态呈现

GitHub Actions 负责“运行状态”，业务卡片仍由 Radar 自身负责。

CLI 已把业务结果映射为退出码：

- `success` → exit 0
- `partial` → exit 1
- `failed` → exit 1
- `skipped` → exit 0

Workflow 在 `if: always()` 步骤执行：

```bash
python -m app.cli status
```

并把输出写入 `$GITHUB_STEP_SUMMARY`，使每次 Actions Run 能直接看到：

- 最近执行状态
- 执行编号
- 项目数量
- 政策数量
- 数据库保存数量
- AI fallback 数量
- 飞书发送状态
- 耗时
- 待补发 Outbox 数量
- 最新数据库备份

同时上传运行日志 Artifact，便于失败诊断。

## 10. 异常行为

### Preflight / 采集 / DeepSeek / 数据库异常

沿用现有 `run_daily_radar()` 的 `partial` / `failed` 判定；Actions Job 对应显示失败。

### 飞书暂时不可用

沿用现有 Outbox：卡片先持久化到 `data/feishu-outbox/`，下一次运行恢复 Cache 后继续补发。

### Cache 恢复失败

Workflow 不阻塞首次运行，但会在 Step Summary 明确显示“无历史状态”。该轮仍能生成日报；历史去重能力会临时降级。

### Cache 保存失败

Artifact 仍作为人工恢复备份；Workflow Summary 标记状态持久化异常。

### Product Hunt 未配置 Token

保持现有降级行为，不阻塞其余来源。

## 11. 安全

- Workflow 只申请 `contents: read`。
- 不允许 PR 事件执行生产日报，避免外部提交读取 Secrets。
- 只允许 `schedule` 与 `workflow_dispatch`。
- Actions 日志不打印 Secret 值。
- `data/` Artifact 不包含 API Key；现有数据库/运行历史设计本身不保存密钥。
- 飞书 Webhook 继续只通过环境变量注入。

## 12. 代码改动范围

预计修改：

```text
.github/workflows/daily-radar.yml      新增生产日报 Workflow
README.md                              增加 GitHub Actions 无服务器部署说明
DEPLOYMENT.md / RUNBOOK.md             增加 Actions 运维与恢复说明（按现有文档结构选取）
```

必要时新增一个很薄的 Actions 辅助脚本，仅负责状态摘要/状态持久化，不允许复制业务分析逻辑。

原则上不修改：

```text
app/pipeline.py
app/ai/*
app/sources/*
app/cards/*
app/feishu.py
```

除非测试暴露出“临时 Runner 环境”特有兼容问题。

## 13. 测试与验收

代码层：

- 现有 pytest 全量通过。
- `python -m compileall -q app scripts tests` 通过。
- `python -m app.cli check` 在测试配置下通过。
- Workflow YAML 可解析。

Actions 层：

1. 手动 `workflow_dispatch`。
2. 第一次运行允许无 Cache。
3. 飞书收到与现有生产 Card Builder 相同结构的日报卡片。
4. Run Summary 正确显示执行状态。
5. 产生 `radar-state-*` Cache 和状态 Artifact。
6. 第二次手动运行成功恢复状态，SQLite 与 `run-history.json` 延续。
7. 人为构造飞书失败时 Outbox 被保存，下一轮可继续补发。

## 14. 回滚

该方案不会删除服务器部署能力。

回滚只需禁用或删除 `.github/workflows/daily-radar.yml`，原 Docker / CLI / APScheduler 路径不受影响。

如果未来重新启用 VPS，必须确保只保留一个生产调度入口，避免 Actions 与服务器 Scheduler 同时每天运行。

## 15. 最终架构

```text
GitHub Actions (00:00 UTC / 08:00 Asia/Shanghai)
        │
        ├─ Restore data/ state
        │
        ├─ python -m app.cli run
        │       │
        │       ├─ GitHub / HN / HF / arXiv / Product Hunt
        │       ├─ Amazon / CBP / CPSC / FDA / FCC
        │       ├─ Existing scoring + dedupe
        │       ├─ Existing DeepSeek analysis
        │       ├─ Existing SQLite
        │       └─ Existing Feishu Card Builder + Outbox
        │
        ├─ Actions status summary
        ├─ Save data/ cache
        └─ Upload state/log artifacts
```

核心原则：**GitHub Actions 只替换“长期服务器调度与运行环境”，不替换 AI-Intelligence-Radar 的业务大脑和飞书表现层。**

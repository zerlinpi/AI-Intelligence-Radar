# GitHub Actions 无服务器日报

本项目可以不依赖长期运行的 VPS，直接由 GitHub Actions 每天执行现有生产日报逻辑。

## 核心原则

GitHub Actions **只负责调度、运行环境、状态持久化和运行状态展示**，不重写业务逻辑。

生产链仍然是：

```text
python -m app.cli run
        ↓
run_daily_radar()
        ↓
GitHub / Hacker News / Hugging Face / arXiv / Product Hunt
+ Amazon / CBP / CPSC / FDA / FCC
        ↓
现有清洗 / 去重 / 热度评分 / 商业优先级
        ↓
DeepSeek V4 Pro 深度分析
        ↓
SQLite
        ↓
ReportDecisionModel
        ↓
现有 Card Builder
        ↓
现有 app.feishu
        ↓
与当前生产一致的飞书卡片
```

因此 Actions 版本不会产生另一套“简化卡片”。以下能力全部保持现有实现：

- 决策摘要 / 美国合规雷达 / 产品机会雷达三个逻辑板块
- turquoise / red / orange / blue Header 视觉语义
- 高 / 中 / 低风险标识
- grey 重点决策块
- 官方原文 / 查看项目按钮
- 完整正文，不硬截断
- 18 KiB Payload 软预算
- 自动分页
- 飞书 Outbox
- 429 / 5xx 重试
- plain text fallback

## 调度时间

Workflow：

```text
.github/workflows/daily-radar.yml
```

Cron：

```text
0 0 * * *
```

GitHub Actions Cron 使用 UTC，因此对应：

```text
每天 08:00 Asia/Shanghai
```

同时保留 `workflow_dispatch`，合并到默认分支后可以从 GitHub Actions 页面人工执行一次。

## GitHub Secrets

在仓库中打开：

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

### 必需

```text
LLM_API_KEY
FEISHU_WEBHOOK
```

`LLM_API_KEY` 使用当前 DeepSeek API Key。

`FEISHU_WEBHOOK` 使用当前飞书自定义机器人 Webhook。不要把完整 Webhook 写入 YAML、Issue、日志或公开代码。

### 可选

```text
PRODUCT_HUNT_TOKEN
```

未配置时沿用项目现有 Product Hunt 降级行为，不阻塞其它来源。

### GitHub Token

不需要额外创建 GitHub PAT。Workflow 直接使用：

```text
GITHUB_TOKEN=${{ github.token }}
```

Workflow 权限仅为：

```yaml
permissions:
  contents: read
```

## 状态持久化

GitHub-hosted Runner 每次执行结束都会被销毁，因此 Workflow 会跨运行保存整个 `data/`：

```text
data/radar.db
data/radar.db-wal
data/radar.db-shm
data/run-history.json
data/feishu-outbox/
data/backups/
data/actions-run.log
```

### 主恢复路径：Actions Cache

运行开始使用：

```text
actions/cache/restore@v4
```

恢复最近 `radar-state-*` 状态。

运行结束无论 `success`、`partial` 或 `failed`，都使用：

```text
actions/cache/save@v4
```

保存新的状态 Key。

这样以下行为可以跨临时 Runner 延续：

- SQLite 已分析历史
- 最近已报告内容去重
- 运行历史
- 数据库备份
- 飞书未完成 Outbox

### 第二恢复路径：Artifact

每次运行都会上传：

```text
radar-state-<run_id>-<run_attempt>
```

保留 30 天。

Artifact 用于故障审计和人工恢复，不作为每天正常运行的唯一存储。

## GitHub Actions 状态

每次 Run 的 Summary 会执行现有：

```bash
python -m app.cli status
```

展示：

- 最近执行状态
- execution id
- 项目数量
- 政策数量
- 数据库保存数量
- AI fallback 数量
- 飞书发送状态
- 执行耗时
- 飞书待补发队列
- 数据库备份

CLI 状态与 Actions Job 状态保持对应：

```text
success  → Actions success
partial  → Actions failure（但 data/ 仍保存）
failed   → Actions failure（但 data/ 仍保存）
skipped  → Actions success
```

## 手动验证

生产 Workflow 只有合并到默认分支后，GitHub 的 schedule / workflow_dispatch 才正式作为生产入口使用。

合并后首次操作：

```text
Actions
→ AI 情报雷达日报
→ Run workflow
```

检查：

1. `生产配置预检` 通过。
2. `运行每日情报分析` 执行现有 CLI。
3. 飞书收到与当前生产 Card Builder 相同结构的日报。
4. Run Summary 能看到 `python -m app.cli status` 输出。
5. Run 产生 `radar-state-*` Artifact。
6. 第二次运行能恢复上一轮 Cache。

## 飞书失败恢复

飞书失败时，现有 `app.feishu` 仍先把卡片写入：

```text
data/feishu-outbox/
```

即使当轮 Actions 最终为失败，`if: always()` 的状态保存步骤仍会保存 Outbox。

下一轮恢复 Cache 后，应用继续按现有 Outbox 逻辑补发，不重新实现一套 Actions 消息队列。

## Cache 丢失

如果 GitHub Cache 因过期、清理或其它原因没有恢复：

- Workflow 会创建新的 `data/` 并继续运行。
- 当轮仍能产生飞书日报。
- 历史去重与 SQLite 连续性会临时丢失。

优先从最近成功 Run 的 `radar-state-*` Artifact 人工恢复。

## 不要同时启用两个生产调度器

仓库仍保留 Docker/VPS + APScheduler 能力用于兼容和回滚。

正式切到 GitHub Actions 后，不要同时让服务器上的 Scheduler 每天 08:00 执行，否则可能形成两个独立生产运行环境。

生产环境应二选一：

```text
GitHub Actions
或
VPS / Docker APScheduler
```

本次实现不会删除 VPS 部署路径，因此回滚只需要停用 GitHub Actions 生产 Workflow 并重新启用原 Scheduler。

## 安全边界

生产 Workflow：

- 不在 PR 事件执行。
- 不在 push 事件执行生产日报。
- 不把 Webhook/API Key 硬编码到仓库。
- 不自行通过 `curl` 拼装飞书业务消息。
- 不改变现有 Card Builder。
- 不改变现有 DeepSeek Prompt / scoring / collector。

这保证了无服务器迁移只替换“在哪里每天运行”，不会替换 AI-Intelligence-Radar 的业务大脑和飞书表现层。

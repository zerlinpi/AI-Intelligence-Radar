# GitHub Actions + ChatGPT 每日 AI 情报雷达

本方案不依赖长期运行的 VPS，并把“分析”和“发布”拆成两个明确职责：ChatGPT 负责每天研究和判断最新动态，GitHub Actions 负责每天北京时间 08:00 按仓库现有卡片逻辑发布到飞书。

## 最终生产链

```text
每天 07:45 Asia/Shanghai
ChatGPT 自动研究最新公开动态
        ↓
GitHub / Hacker News / Hugging Face / arXiv / Product Hunt
+ Amazon / CBP / CPSC / FDA / FCC
        ↓
按 AI-Intelligence-Radar 原有原则做新鲜度、增长、工程证据、
商业可执行性、跨境电商和实体产品价值判断
        ↓
读取最近 Feed，抑制语义重复；重大增长 / Release / 规则变化可重新进入
        ↓
最多 4 条合规 + 10 个产品/技术机会
        ↓
写入 GitHub Issue #2: ChatGPT Daily Radar Feed
        ↓
每天 08:00 Asia/Shanghai
GitHub Actions 读取当天 Feed
        ↓
app.chatgpt_feed.report_model_from_dict()
        ↓
ReportDecisionModel
        ↓
现有 app.cards.build_daily_cards()
        ↓
现有 app.feishu.send_feishu_cards()
        ↓
与当前生产一致的飞书卡片
```

GitHub Actions 不再调用第二个 LLM，也不重新采集一次数据，因此不会出现 ChatGPT 已分析一遍、Actions 又让 DeepSeek 重新判断导致结果漂移的问题。

## 飞书样式为什么保持一致

ChatGPT 只输出结构化 Decision Model 数据，不输出飞书 JSON。飞书表现仍完全由仓库现有代码控制：

```text
ReportDecisionModel
→ app.cards
→ priority_builders
→ payload 安全检查 / 自动分页
→ app.feishu
```

因此继续保留：

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

## ChatGPT Feed

专用 Issue：

```text
#2 ChatGPT Daily Radar Feed
```

每天 07:45 的 ChatGPT 自动任务会：

1. 使用最新公开信息研究五类 AI/产品平台与五类美国跨境/合规来源。
2. 优先使用官方/一手来源验证高风险结论。
3. 读取 Issue #2 最近评论，避免重复日报。
4. 只有重大增速、重要 Release、规则版本、执行日期、执法方式或适用范围发生实质变化时，才允许已出现主题重新进入。
5. 输出中文经营判断、最多 3 条 Top Actions、最多 4 条合规、最多 10 个项目。
6. 把机器可读 JSON 评论写回 Issue #2，不写入任何 API Key、Webhook 或 Token。

Feed 标记固定为：

```text
AI-INTELLIGENCE-RADAR-CHATGPT-FEED
```

`date_text` 必须等于当天 Asia/Shanghai 日期，08:00 发布脚本不会误用昨日 Feed。

## 08:00 GitHub Actions 发布

Workflow：

```text
.github/workflows/daily-radar.yml
```

Cron：

```text
0 0 * * *
```

GitHub Actions Cron 使用 UTC，对应：

```text
每天 08:00 Asia/Shanghai
```

同时保留 `workflow_dispatch`。

生产发布脚本：

```bash
python scripts/send_chatgpt_feed.py
```

它只做：

```text
读取 Issue #2 当天 Feed
→ 转换 ReportDecisionModel
→ 调用现有 Card Builder
→ 调用现有 app.feishu
→ 写入 data/chatgpt-feed-status.json
```

不会调用 `python -m app.cli run`，也不会调用 DeepSeek/OpenAI API。

## GitHub 权限

Workflow 只申请：

```yaml
permissions:
  contents: read
  issues: read
```

GitHub Issue 读取使用 Actions 自动提供的：

```text
GITHUB_TOKEN=${{ github.token }}
```

不需要额外 GitHub PAT。

## 飞书发送凭证

仓库代码继续通过环境变量读取：

```text
FEISHU_WEBHOOK
```

Workflow 使用：

```text
${{ secrets.FEISHU_WEBHOOK }}
```

飞书 Hook 不应出现在公开 Workflow、Issue、日志、Artifact 或 Git 历史中。ChatGPT 的 GitHub 连接当前不暴露 GitHub Actions Secrets 写接口，因此代码侧不能安全地把明文 Hook 提交进公开仓库来替代 Secret。

## 状态持久化

GitHub-hosted Runner 是临时环境，因此 Workflow 会跨运行保存 `data/`：

```text
data/feishu-outbox/
data/chatgpt-feed-status.json
data/actions-run.log
```

项目其它既有 `data/` 内容也会一起被保留，以兼容原有数据库/Outbox/回滚路径。

### Actions Cache

运行开始：

```text
actions/cache/restore@v4
```

运行结束，无论成功失败：

```text
actions/cache/save@v4
```

这样飞书未完成 Outbox 可以跨 Runner 继续存在。

### Artifact

每次运行都会上传：

```text
radar-state-<run_id>-<run_attempt>
```

保留 30 天，用于故障审计与人工恢复。

## Actions 状态

每次运行 Summary 展示：

- Feed Issue 编号
- 触发方式
- Workflow Run / attempt
- Cache 是否命中
- 发布退出码
- `data/chatgpt-feed-status.json`
- 现有 `python -m app.cli status` 的 Outbox / Radar 状态

如果当天 07:45 ChatGPT Feed 没有成功生成，08:00 Workflow 会明确失败，而不是拿昨日分析冒充今日数据。

## 飞书失败恢复

卡片仍通过现有 `app.feishu` 发送，并继续使用：

```text
data/feishu-outbox/
```

网络异常、429 / 5xx、进程中断等行为仍沿用现有重试、持久化和 plain text fallback，不在 Actions 里复制另一套发送逻辑。

## 旧 VPS / DeepSeek 路径

原来的：

```text
python -m app.cli run
Docker / APScheduler
DeepSeek 分析
```

仍保留在仓库作为独立部署和回滚能力，本次没有删除 collectors、scoring、DeepSeek、SQLite 或 Scheduler 代码。

正式采用 ChatGPT Feed + GitHub Actions 后，不应再同时启用服务器每天 08:00 的旧 Scheduler，否则可能出现两套日报并行发送。

## 验证

功能分支 CI 覆盖：

- ChatGPT Feed 能转换成现有 `ReportDecisionModel`
- ChatGPT Feed 继续走现有 Card Builder
- 高风险合规仍产生 red Header
- 产品机会仍产生 blue Header
- Workflow 固定 08:00 Asia/Shanghai
- Workflow 不调用第二个 LLM
- Workflow 不自己拼飞书 JSON / curl 请求
- Cache / Artifact / always-save 路径存在
- 原仓库完整 pytest 回归

核心原则：**ChatGPT 负责每天分析最新动态，GitHub Actions 只负责 08:00 发布；飞书长相继续由 AI-Intelligence-Radar 原有 Card Builder 决定。**

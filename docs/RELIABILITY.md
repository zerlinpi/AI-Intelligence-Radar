# AI Intelligence Radar 生产稳定性说明

本项目的稳定性目标不是假设外部 API 永不失败，而是让异常具备：**可预检、可降级、可恢复、可定位**。

## 运行状态

主流程统一返回三种状态：

- `success`：数据库、AI 分析、持久化、飞书通知全部达到预期。
- `partial`：日报已生成，但存在 AI fallback、数据库保存不完整或飞书卡片尚未全部送达。
- `failed`：生产预检、数据库初始化/去重或其他关键阶段失败，本轮停止继续消耗模型。
- `skipped`：已有另一轮任务运行，当前执行主动跳过。

CLI 对 `success/skipped` 返回退出码 0；`partial/failed` 返回非 0。

## 生产预检

执行：

```bash
python -m app.cli check
```

预检只检查本地配置与数据库，不调用 DeepSeek，不向飞书发送消息。

必需项包括：

- SQLite 可连接且 `PRAGMA quick_check` 正常
- 数据库目录可写
- 飞书持久化 outbox 目录可写
- `FEISHU_WEBHOOK` 格式有效
- LLM API Key、Base URL、Model 已配置
- LLM 输出预算至少 8192 Token
- LLM timeout 至少 120 秒
- 飞书 Payload 安全预算在允许范围内
- `REPORT_TIMEZONE` 可解析

GitHub Token 和 Product Hunt Token 属于可选项。

## `/health` 与 `/ready`

`GET /health` 是 liveness，只证明服务进程存活。

`GET /ready` 是 readiness，必须同时满足：

1. APScheduler 正常运行；
2. 生产预检全部通过。

因此容器显示 unhealthy 时，优先执行：

```bash
python -m app.cli check
```

而不是直接删除容器或数据库。

## SQLite 稳定性

文件型 SQLite 使用：

- `journal_mode=WAL`
- `synchronous=NORMAL`
- `busy_timeout=15000`
- Python SQLite connection timeout 15 秒
- SQLAlchemy `pool_pre_ping=True`

目的：降低短暂读写竞争导致的 `database is locked`，并及时识别失效连接。

数据库仍位于：

```text
./data/radar.db
```

Docker 必须保留：

```text
./data:/app/data
```

不要使用会删除服务器其他容器/卷的全局 Docker prune 命令。

## 飞书持久化 Outbox

结构化三卡日报在真正发送前先写入：

```text
./data/feishu-outbox/
```

默认流程：

```text
Card Builder
→ 严格 JSON 校验
→ 写入 outbox（原子写入 + fsync）
→ 按顺序发送 summary / compliance / products
→ 每张成功后立即持久化发送状态
→ 全部成功后删除对应 outbox 文件
```

如果网络、飞书 429/5xx 或容器重启造成部分卡片未发送，下次发送前会优先补发旧队列，只补发未成功的卡片。

损坏的 outbox JSON 会被移动到：

```text
./data/feishu-outbox/bad/
```

避免损坏文件永久阻塞后续日报。

### Webhook 幂等边界

飞书自定义 Webhook 没有项目可控的幂等键，因此无法实现严格 exactly-once。

极端情况下：飞书已经接收成功，但进程在本地写入 `sent=true` 前立即崩溃，下一次恢复可能重复发送该卡片。

当前设计优先选择 **at-least-once**，即最大限度避免漏发；如果未来必须严格 exactly-once，应迁移到具备可追踪消息 ID/业务幂等能力的企业应用发送链路。

## 飞书发送保护

发送前执行：

- `json.dumps(..., allow_nan=False)`，NaN/Infinity 不允许进入飞书。
- 实际 UTF-8 Payload 字节统计。
- 默认 18 KiB 安全预算，且配置不会允许超过 20 KiB。
- 卡片无效或超预算时改发 plain-text fallback。
- 429 / 5xx / timeout / connection error 执行有限指数退避。
- 不可恢复 4xx 不做无意义重复请求。
- 上一张完全失败时停止发送后续卡片，保证顺序。

## AI 分析保护

- DeepSeek 使用内部 SSE 流式接收，降低长时间空闲连接被中间层切断的概率。
- 单次长任务允许较长 timeout。
- 批量结果缺少个别序号时只恢复缺失条目。
- 每个输入必须得到一个分析结果；异常时生成明确 fallback。
- fallback 不作为已成功处理记录永久去重，后续采集到同一 URL 会再次尝试 AI 分析。

## 建议的生产检查

更新容器后：

```bash
python -m app.cli check
```

确认 readiness：

```bash
curl -i http://127.0.0.1:8000/ready
```

手动运行：

```bash
python -m app.cli
```

日志应最终出现：

```text
日报执行完成：执行编号=... 状态=success ...
```

如果出现 `status=partial`，优先搜索：

```text
AI 分析降级
数据库保存不完整
飞书日报未全部送达
飞书持久化队列
```

如果出现 `status=failed`，先修复失败项，再重新执行；不要连续重复触发 DeepSeek 长任务。

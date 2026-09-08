# GitHub Actions Daily Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing AI-Intelligence-Radar production pipeline every day in GitHub Actions without a long-lived server, preserve state between ephemeral runners, and keep the existing Feishu card output exactly on the current Card Builder path.

**Architecture:** GitHub Actions becomes only the scheduler/runtime wrapper. The workflow restores `data/`, installs the existing Python application, runs `python -m app.cli run`, then always emits the existing CLI status into the Actions summary and persists `data/` with cache plus an artifact backup. It does not duplicate collectors, scoring, DeepSeek prompts, Decision Model logic, or Feishu card construction.

**Tech Stack:** GitHub Actions, Python 3.12, existing pytest suite, SQLite, actions/cache v4, actions/upload-artifact v4.

**Spec:** `docs/superpowers/specs/2026-09-07-github-actions-daily-radar-design.md`

## Global Constraints

- Implementation branch only: `feat/github-actions-daily-radar`; do not modify `main` directly.
- Production schedule is `0 0 * * *`, corresponding to 08:00 Asia/Shanghai.
- Production business entry point remains `python -m app.cli run`.
- Existing Feishu Card Builder and `app.feishu` send path must remain unchanged.
- Persist `data/` across runs so SQLite history, duplicate filtering, run history and Feishu Outbox survive ephemeral runners.
- Production secrets are injected only through GitHub Secrets; never hard-code `FEISHU_WEBHOOK`, `LLM_API_KEY`, or `PRODUCT_HUNT_TOKEN`.
- Workflow triggers must be limited to `schedule` and `workflow_dispatch`; no pull-request production execution.
- Workflow permissions are `contents: read` only.
- Existing Docker/VPS scheduler compatibility remains intact.

---

### Task 1: Add a workflow contract regression test

**Files:**
- Create: `tests/test_daily_workflow.py`

**Interfaces:**
- Consumes: `.github/workflows/daily-radar.yml` as text.
- Produces: regression guarantees for schedule, production CLI entry point, state restore/save, status summary, artifacts and Feishu-path preservation.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-radar.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_workflow_uses_existing_production_pipeline():
    text = _workflow_text()
    assert "0 0 * * *" in text
    assert "workflow_dispatch:" in text
    assert "python -m app.cli run" in text
    assert "python -m app.cli status" in text


def test_daily_workflow_preserves_runtime_state_between_runners():
    text = _workflow_text()
    assert "actions/cache/restore@v4" in text
    assert "actions/cache/save@v4" in text
    assert "path: data" in text
    assert "restore-keys:" in text
    assert "radar-state-" in text
    assert "actions/upload-artifact@v4" in text


def test_daily_workflow_keeps_feishu_rendering_inside_application():
    text = _workflow_text()
    assert "FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}" in text
    assert "curl " not in text
    assert "open-apis/bot/v2/hook/" not in text


def test_daily_workflow_has_safe_production_boundaries():
    text = _workflow_text()
    assert "contents: read" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "cancel-in-progress: false" in text
    assert "if: always()" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_workflow.py -v`

Expected: FAIL because `.github/workflows/daily-radar.yml` does not exist.

- [ ] **Step 3: Commit the failing contract test**

```bash
git add tests/test_daily_workflow.py
git commit -m "test: define daily radar workflow contract"
```

---

### Task 2: Add the production GitHub Actions workflow

**Files:**
- Create: `.github/workflows/daily-radar.yml`
- Test: `tests/test_daily_workflow.py`

**Interfaces:**
- Consumes: existing `requirements.txt`, `app.cli`, GitHub Secrets and `data/` runtime paths.
- Produces: scheduled/manual production execution, restored state, Actions summary, cache snapshot and artifact backup.

- [ ] **Step 1: Create the minimal workflow that satisfies the contract**

```yaml
name: AI 情报雷达日报

on:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ai-intelligence-radar-daily
  cancel-in-progress: false

env:
  PYTHONUNBUFFERED: "1"
  REPORT_TIMEZONE: "Asia/Shanghai"
  DATABASE_URL: "sqlite:///./data/radar.db"
  DATABASE_BACKUP_DIR: "./data/backups"
  RUN_HISTORY_FILE: "./data/run-history.json"
  FEISHU_OUTBOX_DIR: "./data/feishu-outbox"
  FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}
  GITHUB_TOKEN: ${{ github.token }}
  PRODUCT_HUNT_TOKEN: ${{ secrets.PRODUCT_HUNT_TOKEN }}
  LLM_PROVIDER: "deepseek"
  LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
  LLM_BASE_URL: "https://api.deepseek.com/v1"
  LLM_MODEL: "deepseek-v4-pro"
  LLM_TEMPERATURE: "0.2"
  LLM_MAX_TOKENS: "131072"
  LLM_TIMEOUT_SECONDS: "900"

jobs:
  daily-radar:
    name: 每日 AI 情报分析
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - name: 获取代码
        uses: actions/checkout@v4

      - name: 配置 Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: 恢复 Radar 状态
        id: radar-cache-restore
        uses: actions/cache/restore@v4
        with:
          path: data
          key: radar-state-${{ runner.os }}-v1-${{ github.run_id }}
          restore-keys: |
            radar-state-${{ runner.os }}-v1-

      - name: 准备运行目录
        run: mkdir -p data data/backups data/feishu-outbox

      - name: 安装依赖
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: 生产配置预检
        run: python -m app.cli check

      - name: 运行每日情报分析
        id: radar-run
        shell: bash
        run: |
          set +e
          python -m app.cli run 2>&1 | tee data/actions-run.log
          radar_exit=${PIPESTATUS[0]}
          echo "exit_code=${radar_exit}" >> "$GITHUB_OUTPUT"
          exit "${radar_exit}"

      - name: 写入 Actions 状态摘要
        if: always()
        shell: bash
        run: |
          {
            echo "## AI 情报雷达运行状态"
            echo
            echo "- 触发方式：${{ github.event_name }}"
            echo "- 状态缓存恢复：${{ steps.radar-cache-restore.outputs.cache-hit == 'true' && '命中精确缓存' || '恢复最新历史状态/首次运行' }}"
            echo "- 日报退出码：${{ steps.radar-run.outputs.exit_code || '未执行到 CLI' }}"
            echo
            echo '```text'
            python -m app.cli status || true
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"

      - name: 保存 Radar 状态缓存
        if: always()
        uses: actions/cache/save@v4
        with:
          path: data
          key: radar-state-${{ runner.os }}-v1-${{ github.run_id }}

      - name: 上传状态与日志备份
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: radar-state-${{ github.run_id }}
          path: data
          if-no-files-found: warn
          retention-days: 30
```

- [ ] **Step 2: Run the workflow contract test**

Run: `python -m pytest tests/test_daily_workflow.py -v`

Expected: PASS.

- [ ] **Step 3: Run the existing CLI/status tests**

Run: `python -m pytest tests/test_cli_status.py -v`

Expected: PASS, proving the workflow is still consuming the existing status interface.

- [ ] **Step 4: Commit the workflow**

```bash
git add .github/workflows/daily-radar.yml
git commit -m "feat: run daily radar with GitHub Actions"
```

---

### Task 3: Document the serverless production path and secret setup

**Files:**
- Modify: `README.md`
- Modify: `DEPLOYMENT.md`
- Modify: `RUNBOOK.md`

**Interfaces:**
- Consumes: workflow contract from Task 2.
- Produces: operator instructions for enabling GitHub Actions, adding Secrets, manual dispatch after merge, cache/artifact recovery and avoiding duplicate VPS scheduling.

- [ ] **Step 1: Update README deployment overview**

Add a `GitHub Actions 无服务器运行` section that states:

```text
每天 08:00 Asia/Shanghai 由 .github/workflows/daily-radar.yml 触发。
Actions 仅替代运行环境与调度，不改变 run_daily_radar()、DeepSeek 分析、Card Builder 或飞书发送逻辑。
必需 Secrets：LLM_API_KEY、FEISHU_WEBHOOK。
可选 Secret：PRODUCT_HUNT_TOKEN。
GITHUB_TOKEN 使用 GitHub Actions 自动令牌。
```

- [ ] **Step 2: Update DEPLOYMENT.md**

Document exact setup:

```text
Repository → Settings → Secrets and variables → Actions → New repository secret

LLM_API_KEY=<DeepSeek API Key>
FEISHU_WEBHOOK=<Feishu custom bot webhook>
PRODUCT_HUNT_TOKEN=<optional>
```

Document that scheduled workflows run from the default branch, so the schedule becomes live only after this feature branch is merged.

- [ ] **Step 3: Update RUNBOOK.md**

Add operational checks:

```text
Actions → AI 情报雷达日报 → latest run
Run Summary → execution status
Artifacts → radar-state-<run_id>
```

Add recovery notes for cache miss, artifact backup, pending Feishu Outbox and the rule that only one scheduler (Actions or VPS APScheduler) should be active in production.

- [ ] **Step 4: Commit the documentation**

```bash
git add README.md DEPLOYMENT.md RUNBOOK.md
git commit -m "docs: document serverless radar operations"
```

---

### Task 4: Full verification and review-ready branch

**Files:**
- Verify: `.github/workflows/daily-radar.yml`
- Verify: `tests/test_daily_workflow.py`
- Verify: existing application and card tests

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a branch ready for PR without touching `main`.

- [ ] **Step 1: Run workflow regression tests**

Run:

```bash
python -m pytest tests/test_daily_workflow.py tests/test_cli_status.py tests/test_cards.py tests/test_card_safety.py -v --tb=short
```

Expected: PASS.

- [ ] **Step 2: Run static Python compilation**

Run:

```bash
python -m compileall -q app scripts tests
```

Expected: exit 0.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
python -m pytest -v --tb=short
```

Expected: PASS.

- [ ] **Step 4: Verify branch diff only contains intended changes**

Expected changed paths:

```text
.github/workflows/daily-radar.yml
tests/test_daily_workflow.py
README.md
DEPLOYMENT.md
RUNBOOK.md
docs/superpowers/plans/2026-09-07-github-actions-daily-radar.md
```

The approved design doc may also appear because the branch was cut after that documentation commit; no production application modules should change.

- [ ] **Step 5: Open a pull request into `main` without merging it**

PR title:

```text
feat: run AI intelligence radar daily with GitHub Actions
```

PR body must state that normal Feishu cards still originate from the existing `ReportDecisionModel → Card Builder → app.feishu` path and therefore retain current rendering and paging behavior.

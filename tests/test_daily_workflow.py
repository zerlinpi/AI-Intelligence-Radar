from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-radar.yml")


def _workflow_text() -> str:
    assert WORKFLOW.exists(), "daily radar production workflow must exist"
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_workflow_has_single_beijing_0800_release_gate():
    text = _workflow_text()
    assert "issue_comment:" not in text
    assert "schedule:" in text
    assert 'cron: "0 23 * * *"' in text
    assert 'cron: "15 0 * * *"' not in text
    assert 'cron: "35 0 * * *"' not in text
    assert 'cron: "0 1 * * *"' not in text
    assert "等待到北京时间 08:00:00" in text
    assert 'ZoneInfo("Asia/Shanghai")' in text
    assert "hour=8, minute=0, second=0" in text
    assert 'RADAR_ENFORCE_SEND_WINDOW: "1"' in text
    assert 'RADAR_SEND_WINDOW_START: "08:00"' in text
    assert 'RADAR_SEND_WINDOW_END: "08:10"' in text
    assert "workflow_dispatch:" in text
    assert 'CHATGPT_FEED_ISSUE: "2"' in text
    assert "CHATGPT_FEED_AUTHOR: ${{ github.repository_owner }}" in text
    assert "python scripts/send_chatgpt_feed.py" in text
    assert "python -m app.cli run" not in text


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
    assert "python scripts/send_chatgpt_feed.py" in text
    assert "curl " not in text
    assert "open-apis/bot/v2/hook/" not in text
    assert '"msg_type"' not in text
    assert '"card"' not in text


def test_daily_workflow_does_not_run_a_second_llm():
    text = _workflow_text()
    assert "LLM_API_KEY" not in text
    assert "LLM_PROVIDER" not in text
    assert "deepseek" not in text.lower()
    assert "PRODUCT_HUNT_TOKEN" not in text


def test_daily_workflow_has_production_boundaries():
    text = _workflow_text()
    assert "contents: read" in text
    assert "issues: write" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 90" in text
    assert "if: always()" in text

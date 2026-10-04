from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-radar.yml")


def _workflow_text() -> str:
    assert WORKFLOW.exists(), "daily radar production workflow must exist"
    return WORKFLOW.read_text(encoding="utf-8")


def test_actions_is_0802_disaster_recovery_runner():
    text = _workflow_text()
    assert "issue_comment:" not in text
    assert "schedule:" in text
    assert 'cron: "15 18 * * *"' in text
    assert 'cron: "30 18 * * *"' in text
    assert "等待到北京时间 08:04 灾备检查" in text
    assert 'ZoneInfo("Asia/Shanghai")' in text
    assert "hour=8, minute=4, second=0" in text
    assert 'RADAR_ENFORCE_SEND_WINDOW: "1"' in text
    assert 'RADAR_SEND_WINDOW_START: "08:00"' in text
    assert 'RADAR_SEND_WINDOW_END: "08:10"' in text
    assert "RADAR_ALLOW_LATE_RECOVERY:" in text
    assert 'RADAR_LOCAL_FALLBACK_PATH: "./data/local-fallback-cards.json"' in text
    assert "07:35 准备本地兜底" in text
    assert "python scripts/prepare_local_fallback.py" in text
    assert "hour=7, minute=35, second=0" in text
    assert "workflow_dispatch:" in text
    assert "force_send:" in text
    assert 'CHATGPT_FEED_ISSUE: "2"' in text
    assert "CHATGPT_FEED_AUTHOR: ${{ github.repository_owner }}" in text
    assert "python scripts/send_chatgpt_feed.py" in text
    assert "常驻 APScheduler" in text


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
    assert "\n  push:\n" not in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 360" in text
    assert "if: always()" in text

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-radar.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_radar_has_feed_trigger_and_scheduled_fallback():
    text = _workflow_text()

    assert "types: [created]" in text
    assert "types: [created, edited]" not in text
    assert "\n  schedule:\n" in text
    assert 'cron: "10 0 * * *"' in text
    assert "\n  push:\n" not in text
    assert "workflow_dispatch:" in text
    assert "cancel-in-progress: false" in text


def test_feed_comment_waits_until_0800_shanghai_before_sending():
    text = _workflow_text()

    assert "等待到上海时间 08:00" in text
    assert 'ZoneInfo("Asia/Shanghai")' in text
    assert "hour=8, minute=0, second=0" in text
    assert "time.sleep(delay)" in text
    assert "timeout-minutes: 60" in text
    assert "发布当天 ChatGPT 情报分析" in text


def test_public_issue_comment_trigger_is_owner_only():
    text = _workflow_text()

    assert "github.event.issue.number == 2" in text
    assert "github.event.comment.user.login == github.repository_owner" in text
    assert "CHATGPT_FEED_AUTHOR: ${{ github.repository_owner }}" in text

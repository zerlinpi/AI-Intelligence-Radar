from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-radar.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_radar_has_one_automatic_trigger_from_new_feed_comment():
    text = _workflow_text()

    assert "\n  schedule:\n" not in text
    assert "types: [created]" in text
    assert "types: [created, edited]" not in text
    assert "\n  push:\n" not in text
    assert "workflow_dispatch:" in text


def test_feed_comment_waits_until_0800_shanghai_before_sending():
    text = _workflow_text()

    assert "等待到上海时间 08:00" in text
    assert "ZoneInfo(\"Asia/Shanghai\")" in text
    assert "hour=8, minute=0, second=0" in text
    assert "time.sleep(delay)" in text
    assert "发布当天 ChatGPT 情报分析" in text

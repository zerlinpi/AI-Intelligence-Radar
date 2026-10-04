from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-radar.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_radar_uses_early_wakeup_redundancy():
    text = _workflow_text()

    assert "issue_comment:" not in text
    assert "\n  schedule:\n" in text
    assert text.count('cron: "15 18 * * *"') == 1
    assert text.count('cron: "30 18 * * *"') == 1
    assert 'cron: "0 23 * * *"' not in text
    assert "\n  push:\n" not in text
    assert "workflow_dispatch:" in text
    assert "force_send:" in text
    assert "cancel-in-progress: false" in text


def test_release_runner_waits_until_0800_shanghai_before_sending():
    text = _workflow_text()

    assert "等待到北京时间 08:00:00" in text
    assert 'ZoneInfo("Asia/Shanghai")' in text
    assert "hour=8, minute=0, second=0" in text
    assert "time.sleep(delay)" in text
    assert "timeout-minutes: 360" in text
    assert "发布当天 ChatGPT 情报分析" in text


def test_late_manual_dispatch_requires_explicit_force_send():
    text = _workflow_text()

    assert 'RADAR_ENFORCE_SEND_WINDOW: "1"' in text
    assert 'RADAR_SEND_WINDOW_START: "08:00"' in text
    assert 'RADAR_SEND_WINDOW_END: "08:10"' in text
    assert "RADAR_ALLOW_LATE_RECOVERY:" in text
    assert "inputs.force_send" in text


def test_release_runner_prepares_local_fallback_before_0800():
    text = _workflow_text()

    assert "07:35 准备本地兜底" in text
    assert "python scripts/prepare_local_fallback.py" in text
    assert "hour=7, minute=35, second=0" in text
    assert 'RADAR_LOCAL_FALLBACK_PATH: "./data/local-fallback-cards.json"' in text

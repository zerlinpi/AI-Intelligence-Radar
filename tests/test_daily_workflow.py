from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-radar.yml")


def _workflow_text() -> str:
    assert WORKFLOW.exists(), "daily radar production workflow must exist"
    return WORKFLOW.read_text(encoding="utf-8")


def test_daily_workflow_uses_existing_production_pipeline():
    text = _workflow_text()
    assert 'cron: "0 0 * * *"' in text
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

from sqlalchemy import text

from app.core import preflight
from app.database.session import engine


def _valid_runtime(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setattr(preflight, "FEISHU_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
    monkeypatch.setattr(preflight, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(preflight, "LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr(preflight, "LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(preflight, "LLM_MAX_TOKENS", 65536)
    monkeypatch.setattr(preflight, "LLM_TIMEOUT_SECONDS", 900)
    monkeypatch.setattr(preflight, "FEISHU_MAX_PAYLOAD_BYTES", 18 * 1024)
    monkeypatch.setattr(preflight, "REPORT_TIMEZONE", "Asia/Shanghai")


def test_preflight_passes_with_valid_local_runtime(monkeypatch):
    _valid_runtime(monkeypatch)
    result = preflight.run_preflight()
    assert result.ok is True
    assert result.failures == []


def test_preflight_rejects_invalid_timezone(monkeypatch):
    _valid_runtime(monkeypatch)
    monkeypatch.setattr(preflight, "REPORT_TIMEZONE", "Mars/Olympus")
    result = preflight.run_preflight()
    assert result.ok is False
    assert "日报时区" in result.failures


def test_preflight_rejects_too_small_model_budget(monkeypatch):
    _valid_runtime(monkeypatch)
    monkeypatch.setattr(preflight, "LLM_MAX_TOKENS", 1024)
    result = preflight.run_preflight()
    assert result.ok is False
    assert "模型输出上限" in result.failures


def test_sqlite_busy_timeout_is_enabled():
    with engine.connect() as connection:
        value = connection.execute(text("PRAGMA busy_timeout")).scalar()
    assert int(value or 0) >= 15000



def test_production_preflight_requires_publisher_coordination(monkeypatch):
    _valid_runtime(monkeypatch)
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.delenv("RADAR_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("RADAR_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = preflight.run_preflight()

    assert result.ok is False
    assert "08:00 GitHub 发布协调" in result.failures


def test_production_preflight_accepts_dedicated_publisher_token(monkeypatch):
    _valid_runtime(monkeypatch)
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("RADAR_GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("RADAR_GITHUB_TOKEN", "test-token")

    result = preflight.run_preflight()

    assert "08:00 GitHub 发布协调" not in result.failures

from sqlalchemy import text

from app.core import preflight
from app.database.session import engine


def _valid_runtime(monkeypatch):
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

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.radar_item import RadarItem


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_local_fallback.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_local_fallback_test_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "zerlinpi/AI-Intelligence-Radar")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CHATGPT_FEED_AUTHOR", "zerlinpi")
    monkeypatch.setenv("CHATGPT_FEED_ISSUE", "2")
    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-10-03")


def test_prepare_skips_when_chatgpt_feed_exists(monkeypatch, tmp_path):
    module = _load_module()
    _env(monkeypatch)
    target = tmp_path / "fallback.json"
    target.write_text("stale", encoding="utf-8")

    monkeypatch.setattr(module, "_has_chatgpt_feed", lambda *args, **kwargs: True)

    def should_not_collect():
        raise AssertionError("collectors must not run when ChatGPT Feed already exists")

    monkeypatch.setattr(module, "collect_sources", should_not_collect)
    monkeypatch.setattr(module, "collect_policies", should_not_collect)

    result = module.prepare(target)

    assert result["status"] == "skipped"
    assert not target.exists()


def test_prepare_builds_cards_when_feed_is_missing(monkeypatch, tmp_path):
    module = _load_module()
    _env(monkeypatch)
    target = tmp_path / "fallback.json"

    project = RadarItem(
        title="Agent Tool",
        source="github",
        url="https://github.com/example/agent-tool",
        description="A practical agent automation toolkit for repeatable workflows.",
        created_at=datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc),
        trend_score=82,
        metrics={
            "selection_score": 78,
            "priority_tags": ["跨境电商", "Agent"],
            "stars": 500,
            "forks": 40,
        },
    )
    policy = RadarItem(
        title="Product safety update",
        source="cpsc_compliance",
        url="https://www.cpsc.gov/example",
        description="Official safety update affecting consumer products.",
        category="policy",
        created_at=datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc),
        metrics={
            "policy_focus": "产品合规审核",
            "policy_source": "CPSC",
            "policy_authority": "CPSC",
            "policy_kind": "safety",
            "policy_score": 85,
        },
    )

    monkeypatch.setattr(module, "_has_chatgpt_feed", lambda *args, **kwargs: False)
    monkeypatch.setattr(module, "collect_sources", lambda: [])
    monkeypatch.setattr(module, "collect_policies", lambda: [])
    monkeypatch.setattr(module, "select_project_candidates", lambda items: [project])
    monkeypatch.setattr(module, "select_policy_candidates", lambda items: [policy])

    result = module.prepare(target)

    assert result["status"] == "prepared"
    assert result["cards"] >= 1
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["date"] == "2026-10-03"
    assert record["source"] == "local_deterministic_fallback"
    assert record["cards"]
    assert all("card_type" in card for card in record["cards"])

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


def _items():
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
    return project, policy


def test_prepare_always_builds_fallback_without_github_dependency(monkeypatch, tmp_path):
    module = _load_module()
    target = tmp_path / "fallback.json"
    project, policy = _items()

    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-10-03")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("CHATGPT_FEED_AUTHOR", raising=False)
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


def test_prepare_atomically_replaces_stale_fallback(monkeypatch, tmp_path):
    module = _load_module()
    target = tmp_path / "fallback.json"
    target.write_text('{"date":"2026-10-02"}', encoding="utf-8")
    project, policy = _items()

    monkeypatch.setenv("CHATGPT_FEED_DATE", "2026-10-03")
    monkeypatch.setattr(module, "collect_sources", lambda: [])
    monkeypatch.setattr(module, "collect_policies", lambda: [])
    monkeypatch.setattr(module, "select_project_candidates", lambda items: [project])
    monkeypatch.setattr(module, "select_policy_candidates", lambda items: [policy])

    module.prepare(target)

    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["date"] == "2026-10-03"
    assert not list(tmp_path.glob(".fallback.json.*.tmp"))

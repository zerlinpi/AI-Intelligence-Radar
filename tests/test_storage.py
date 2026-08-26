from datetime import datetime
from types import SimpleNamespace

from app.storage import repository
from app.storage.repository import exists, save_batch


class FakeQuery:
    def __init__(self, record=None):
        self._record = record

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._record


class FakeDB:
    def __init__(self, record=None):
        self.items = []
        self.record = record
        self.commits = 0

    def query(self, _model):
        return FakeQuery(self.record)

    def add(self, item):
        self.items.append(item)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def refresh(self, _item):
        pass


def test_repository_save_batch_deduplicates_with_existing_url(monkeypatch):
    db = FakeDB()

    monkeypatch.setattr(
        "app.storage.repository.exists",
        lambda _db, url: url == "https://example.com/existing",
    )

    result = save_batch(
        db,
        [
            {"title": "Existing", "url": "https://example.com/existing"},
            {"title": "New", "url": "https://example.com/new"},
        ],
    )

    assert len(result) == 1


def test_repository_preserves_source_created_at():
    db = FakeDB()

    result = save_batch(
        db,
        [
            {
                "title": "Recent Project",
                "url": "https://example.com/recent",
                "created_at": "2026-08-25T12:30:00Z",
            }
        ],
    )

    assert len(result) == 1
    assert result[0].created_at == datetime(2026, 8, 25, 12, 30, 0)


def test_fallback_record_is_not_treated_as_completed():
    record = SimpleNamespace(
        analysis={
            "purpose": "项目原始说明：demo",
            "llm_meta": {
                "success": False,
                "fallback": True,
                "reason": "Request timed out.",
            },
        }
    )
    db = FakeDB(record)

    assert exists(db, "https://example.com/retry") is False


def test_new_fallback_result_is_not_saved():
    db = FakeDB()

    result = save_batch(
        db,
        [
            {
                "title": "Retry Later",
                "url": "https://example.com/retry-later",
                "analysis": {
                    "purpose": "项目原始说明：demo",
                    "summary": "本条 AI 深度分析未完成。",
                    "llm_meta": {
                        "success": False,
                        "fallback": True,
                        "reason": "Request timed out.",
                    },
                },
            }
        ],
    )

    assert result == []
    assert db.items == []
    assert db.commits == 0


def test_successful_analysis_overwrites_old_fallback(monkeypatch):
    old = SimpleNamespace(
        source="github",
        title="Old",
        url="https://example.com/retry",
        description="old",
        category="ai",
        trend_score=0,
        business_score=0,
        metrics={},
        analysis={
            "llm_meta": {
                "success": False,
                "fallback": True,
                "reason": "Request timed out.",
            }
        },
        created_at=datetime(2026, 8, 25, 10, 0, 0),
    )
    db = FakeDB(old)

    result = save_batch(
        db,
        [
            {
                "source": "github",
                "title": "Recovered",
                "url": "https://example.com/retry",
                "description": "new description",
                "created_at": "2026-08-25T12:30:00Z",
                "trend_score": 88,
                "metrics": {"stars": 100},
                "analysis": {
                    "purpose": "完整产品描述",
                    "summary": "值得关注",
                    "business_score": 91,
                    "opportunity": "high",
                    "startup_ideas": ["产品方向"],
                    "llm_meta": {
                        "success": True,
                        "fallback": False,
                    },
                },
            }
        ],
    )

    assert len(result) == 1
    assert result[0] is old
    assert old.title == "Recovered"
    assert old.business_score == 91
    assert old.analysis["llm_meta"]["success"] is True
    assert db.items == []
    assert db.commits == 1


def test_material_update_overwrites_existing_success_snapshot():
    old = SimpleNamespace(
        source="github",
        title="acme/edge-camera",
        url="https://github.com/acme/edge-camera",
        description="old edge camera runtime",
        category="ai",
        trend_score=60,
        business_score=75,
        metrics={"stars": 80},
        analysis={
            "purpose": "旧分析",
            "summary": "旧判断",
            "business_score": 75,
            "opportunity": "medium",
            "llm_meta": {"success": True, "fallback": False},
        },
        created_at=datetime(2026, 8, 25, 10, 0, 0),
    )
    db = FakeDB(old)

    result = save_batch(
        db,
        [
            {
                "source": "github",
                "title": "acme/edge-camera",
                "url": "https://github.com/acme/edge-camera",
                "description": "new edge camera runtime with BLE sensor product integration",
                "created_at": "2026-08-25T10:00:00Z",
                "trend_score": 92,
                "metrics": {
                    "stars": 320,
                    "history_material_update": True,
                    "history_material_update_reason": "GitHub Star 显著增长：80→320",
                },
                "analysis": {
                    "purpose": "新版产品能力",
                    "summary": "增长和硬件产品价值均明显提升",
                    "business_score": 90,
                    "opportunity": "high",
                    "llm_meta": {"success": True, "fallback": False},
                },
            }
        ],
    )

    assert len(result) == 1
    assert result[0] is old
    assert old.metrics["stars"] == 320
    assert old.metrics["history_material_update"] is True
    assert old.business_score == 90
    assert old.analysis["purpose"] == "新版产品能力"
    assert db.items == []
    assert db.commits == 1

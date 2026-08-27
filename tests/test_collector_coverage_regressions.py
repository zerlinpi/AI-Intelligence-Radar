import requests

from app.source_coverage import coverage_snapshot, record_collector_health, reset_collection_health
from app.sources import github, producthunt
from app.sources.base import BaseCollector


class _EmptyMappingCollector(BaseCollector):
    name = "empty-mapping"

    def collect(self):
        return {}


class _JsonResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _record_other_sources():
    for source in ("hackernews", "huggingface", "arxiv", "producthunt"):
        record_collector_health(
            source,
            {
                "source": source,
                "success": True,
                "available": True,
                "partial": False,
                "result_count": 0,
            },
        )
    record_collector_health(
        "policy",
        {
            "source": "policy",
            "success": True,
            "available": True,
            "partial": False,
            "result_count": 0,
            "policy_sources": {
                "failed_authorities": [],
                "degraded_authorities": [],
            },
        },
    )


def test_empty_mapping_is_invalid_result_not_successful_empty():
    collector = _EmptyMappingCollector()

    assert collector.collect_safe() == []
    health = collector.get_last_health()

    assert health["success"] is False
    assert health["result_count"] == 0
    assert "返回类型无效" in health["error"]


def test_producthunt_graphql_errors_are_reported_as_source_failure(monkeypatch):
    monkeypatch.setenv("PRODUCT_HUNT_TOKEN", "test-token")
    monkeypatch.setattr(
        producthunt.requests,
        "post",
        lambda *args, **kwargs: _JsonResponse(
            {"errors": [{"message": "temporary upstream GraphQL failure"}]}
        ),
    )

    collector = producthunt.ProductHuntCollector()
    assert collector.collect_safe() == []
    health = collector.get_last_health()

    assert health["success"] is False
    assert health["available"] is True
    assert "GraphQL" in health["error"]


def test_github_partial_search_keeps_data_semantics_but_marks_coverage_degraded(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        assert url == github.SEARCH_API
        calls["count"] += 1
        if calls["count"] == 1:
            return _JsonResponse({"items": []})
        raise requests.ConnectionError("search shard unavailable")

    monkeypatch.setattr(github.requests, "get", fake_get)
    reset_collection_health()

    collector = github.GithubCollector()
    assert collector.collect_safe(limit=5) == []
    health = collector.get_last_health()

    assert health["success"] is True
    assert health["partial"] is True
    assert health["result_count"] == 0
    assert "成功 1/" in health["error"]

    _record_other_sources()
    coverage = coverage_snapshot()
    assert coverage["available"] is True
    assert coverage["complete"] is False
    assert coverage["project_complete"] is False
    assert coverage["project_failed"] == []
    assert coverage["project_degraded"] == ["GitHub"]
    assert "项目源部分降级：GitHub" in coverage["note"]
    assert "不能把缺失数据解释为“没有变化”" in coverage["note"]
    reset_collection_health()


def test_github_all_search_queries_failed_is_not_successful_empty(monkeypatch):
    monkeypatch.setattr(
        github.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("github search unavailable")
        ),
    )
    reset_collection_health()

    collector = github.GithubCollector()
    assert collector.collect_safe(limit=5) == []
    health = collector.get_last_health()

    assert health["success"] is False
    assert health["available"] is True
    assert health["partial"] is False
    assert health["result_count"] == 0
    assert "所有搜索查询均失败" in health["error"]
    reset_collection_health()

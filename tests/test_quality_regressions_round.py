from datetime import datetime, timezone

from app.cleaner import normalize_items
from app.deployment_readiness import attach_deployment_metrics, github_engineering_readiness
from app.models.radar_item import RadarItem
from app.source_coverage import (
    coverage_snapshot,
    record_collector_health,
    reset_collection_health,
)
from app.sources.github import _engineering_tree_profile


PROJECT_SOURCES = ("github", "hackernews", "huggingface", "arxiv", "producthunt")


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_same_external_url_merges_cross_source_metrics_instead_of_dropping_second_source():
    url = "https://github.com/acme/seller-radar"
    items = [
        {
            "source": "github",
            "title": "acme/seller-radar",
            "url": url,
            "description": "Amazon seller listing automation SDK",
            "metrics": {"stars": 320, "language": "Python"},
        },
        {
            "source": "hackernews",
            "title": "Show HN: Seller Radar launch",
            "url": url,
            "description": "Seller Radar automates Amazon listing workflows for merchants",
            "metrics": {"upvotes": 140, "comments": 22},
        },
    ]

    result = normalize_items(items)

    assert len(result) == 1
    metrics = result[0]["metrics"]
    assert metrics["stars"] == 320
    assert metrics["upvotes"] == 140
    assert metrics["comments"] == 22
    assert set(metrics["also_seen_on"]) == {"github", "hackernews"}


def test_github_tree_profile_exposes_code_package_deployment_test_and_ci_assets():
    profile = _engineering_tree_profile(
        [
            "src/radar/__init__.py",
            "src/radar/client.py",
            "src/radar/pipeline.py",
            "src/radar/scoring.py",
            "src/radar/storage.py",
            "pyproject.toml",
            "Dockerfile",
            "tests/test_pipeline.py",
            ".github/workflows/test.yml",
            "README.md",
        ]
    )

    assert profile["engineering_tree_evidence"] is True
    assert profile["repo_file_count"] == 10
    assert profile["repo_code_file_count"] >= 6
    assert "pyproject.toml" in profile["package_config_files"]
    assert "Dockerfile" in profile["deployment_files"]
    assert profile["test_files"]
    assert profile["ci_files"]


def test_github_successful_tree_with_almost_no_code_overrides_hype_metadata():
    item = {
        "source": "github",
        "metrics": {
            "primary_lane": "开发基础设施",
            "repo_size_kb": 5000,
            "language": "Python",
            "readme_evidence": True,
            "readme_chars": 4000,
            "pushed_at": _now(),
            "commercial_license_status": "permissive",
            "engineering_tree_evidence": True,
            "repo_file_count": 40,
            "repo_code_file_count": 1,
            "package_config_files": [],
            "deployment_files": [],
            "test_files": [],
            "ci_files": [],
        },
    }

    result = github_engineering_readiness(item)

    assert result["eligible"] is False
    assert "实际代码文件不足" in result["reason"]


def test_github_tree_evidence_survives_radar_serialization_for_deepseek():
    item = {
        "source": "github",
        "metrics": {
            "opportunity_evidence": ["runtime"],
            "engineering_tree_evidence": True,
            "repo_file_count": 80,
            "repo_code_file_count": 35,
            "package_config_files": ["pyproject.toml"],
            "deployment_files": ["Dockerfile"],
            "test_files": ["tests/test_runtime.py"],
            "ci_files": [".github/workflows/test.yml"],
        },
    }
    readiness = {
        "eligible": True,
        "score": 91,
        "reason": "具备真实文件树工程资产",
        "evidence": [
            "文件树:80文件/35代码文件",
            "包/构建配置:pyproject.toml",
            "部署配置:Dockerfile",
            "测试资产:存在",
            "CI资产:存在",
        ],
    }
    attach_deployment_metrics(item, readiness)

    radar = RadarItem.from_dict(
        {
            "source": "github",
            "title": "acme/runtime",
            "url": "https://github.com/acme/runtime",
            "metrics": item["metrics"],
        }
    )
    serialized = radar.to_dict()
    evidence = serialized["metrics"]["opportunity_evidence"]

    assert any(str(value).startswith("部署成熟度:") for value in evidence)
    assert any("文件树:80文件/35代码文件" in str(value) for value in evidence)


def test_unavailable_project_source_makes_coverage_incomplete_not_empty_success():
    reset_collection_health()
    for source in PROJECT_SOURCES:
        record_collector_health(
            source,
            {
                "source": source,
                "success": source != "producthunt",
                "available": source != "producthunt",
                "result_count": 0,
            },
        )
    record_collector_health(
        "policy",
        {
            "source": "policy",
            "success": True,
            "available": True,
            "result_count": 0,
            "policy_sources": {
                "failed_authorities": [],
                "degraded_authorities": [],
            },
        },
    )

    coverage = coverage_snapshot()

    assert coverage["available"] is True
    assert coverage["complete"] is False
    assert coverage["project_complete"] is False
    assert coverage["project_failed"] == []
    assert coverage["project_unavailable"] == ["Product Hunt"]
    assert "项目源不可用：Product Hunt" in coverage["note"]
    assert "不能把缺失数据解释为“没有变化”" in coverage["note"]
    reset_collection_health()

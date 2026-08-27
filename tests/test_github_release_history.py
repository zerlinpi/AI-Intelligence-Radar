from datetime import datetime, timedelta, timezone

from app.deployment_readiness import github_engineering_readiness
from app.history_novelty import _project_material_update_reason


def _iso(delta=timedelta()):
    return (datetime.now(timezone.utc) + delta).isoformat()


def _project(*, pushed_at, description=None, **metrics):
    return {
        "source": "github",
        "url": "https://github.com/owner/repo",
        "title": "owner/repo",
        "description": description
        or "Production SDK for Amazon seller workflow automation with reusable APIs and deployment support.",
        "metrics": {
            "pushed_at": pushed_at,
            "stars": 100,
            "forks": 10,
            **metrics,
        },
    }


def test_new_release_tag_is_material_update_even_when_readme_is_unchanged():
    previous = _project(
        pushed_at=_iso(-timedelta(days=2)),
        latest_release_tag="v1.0.0",
        latest_release_published_at=_iso(-timedelta(days=10)),
        history_processed_at=_iso(-timedelta(days=1)),
    )
    current = _project(
        pushed_at=_iso(),
        latest_release_tag="v2.0.0",
        latest_release_published_at=_iso(-timedelta(hours=2)),
    )

    reason = _project_material_update_reason(current, previous)
    assert "v1.0.0→v2.0.0" in reason


def test_first_observed_release_only_reenters_if_published_after_previous_radar_run():
    processed = datetime.now(timezone.utc) - timedelta(days=1)
    previous = _project(
        pushed_at=(processed - timedelta(days=1)).isoformat(),
        latest_release_tag="",
        history_processed_at=processed.isoformat(),
    )

    old_release = _project(
        pushed_at=_iso(),
        latest_release_tag="v1.4.0",
        latest_release_published_at=(processed - timedelta(days=20)).isoformat(),
    )
    new_release = _project(
        pushed_at=_iso(),
        latest_release_tag="v1.5.0",
        latest_release_published_at=(processed + timedelta(hours=2)).isoformat(),
    )

    assert _project_material_update_reason(old_release, previous) == ""
    assert "上次日报后发布正式版本" in _project_material_update_reason(new_release, previous)


def test_new_deployment_asset_is_material_but_more_commits_alone_are_not():
    previous = _project(
        pushed_at=_iso(-timedelta(days=2)),
        engineering_tree_evidence=True,
        repo_code_file_count=20,
        package_config_files=["pyproject.toml"],
        deployment_files=[],
        recent_commit_activity_checked=True,
        recent_commit_sample_count=2,
    )
    commit_only = _project(
        pushed_at=_iso(),
        engineering_tree_evidence=True,
        repo_code_file_count=20,
        package_config_files=["pyproject.toml"],
        deployment_files=[],
        recent_commit_activity_checked=True,
        recent_commit_sample_count=10,
    )
    with_deploy = _project(
        pushed_at=_iso(),
        engineering_tree_evidence=True,
        repo_code_file_count=20,
        package_config_files=["pyproject.toml"],
        deployment_files=["Dockerfile"],
        recent_commit_activity_checked=True,
        recent_commit_sample_count=10,
    )

    assert _project_material_update_reason(commit_only, previous) == ""
    assert "新增部署资产" in _project_material_update_reason(with_deploy, previous)


def test_significant_code_asset_expansion_can_reenter_without_readme_rewrite():
    previous = _project(
        pushed_at=_iso(-timedelta(days=3)),
        engineering_tree_evidence=True,
        repo_code_file_count=10,
        package_config_files=["pyproject.toml"],
        deployment_files=[],
    )
    current = _project(
        pushed_at=_iso(),
        engineering_tree_evidence=True,
        repo_code_file_count=25,
        package_config_files=["pyproject.toml"],
        deployment_files=[],
    )

    reason = _project_material_update_reason(current, previous)
    assert "代码资产显著扩展" in reason


def test_readiness_uses_verified_default_branch_commits_and_release_evidence():
    item = {
        "source": "github",
        "metrics": {
            "primary_lane": "开发基础设施",
            "repo_size_kb": 600,
            "language": "Python",
            "readme_evidence": True,
            "readme_chars": 1600,
            "pushed_at": _iso(),
            "commercial_license_status": "permissive",
            "engineering_tree_evidence": True,
            "repo_file_count": 80,
            "repo_code_file_count": 40,
            "package_config_files": ["pyproject.toml"],
            "deployment_files": ["Dockerfile"],
            "test_files": ["tests/test_core.py"],
            "ci_files": [".github/workflows/test.yml"],
            "recent_commit_activity_checked": True,
            "recent_commit_window_days": 14,
            "recent_commit_sample_count": 6,
            "latest_release_tag": "v2.2.0",
            "latest_release_published_at": _iso(-timedelta(days=2)),
        },
    }

    result = github_engineering_readiness(item)
    assert result["eligible"] is True
    assert any("默认分支提交样本:6" in value for value in result["evidence"])
    assert any("正式Release:v2.2.0" in value for value in result["evidence"])
    assert any("Release近30天" in value for value in result["evidence"])
    assert "版本/提交活动" in result["reason"]


def test_verified_zero_commits_does_not_claim_recent_code_commit():
    item = {
        "source": "github",
        "metrics": {
            "primary_lane": "跨境业务工具",
            "repo_size_kb": 200,
            "language": "Python",
            "readme_evidence": True,
            "readme_chars": 800,
            "pushed_at": _iso(),
            "commercial_license_status": "permissive",
            "recent_commit_activity_checked": True,
            "recent_commit_window_days": 14,
            "recent_commit_sample_count": 0,
        },
    }

    result = github_engineering_readiness(item)
    assert any("默认分支未发现提交" in value for value in result["evidence"])
    assert "近14天有代码提交" not in result["evidence"]

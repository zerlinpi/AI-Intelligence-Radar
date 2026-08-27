from datetime import datetime, timedelta, timezone

from app.cards.priority_builders import _github_growth_signal
from app.github_activity import attach_github_activity_metrics, github_activity_profile
from app.scoring import age_hours, calculate_score
from app.sources import github


class FakeResponse:
    def __init__(self, *, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_github_activity_profile_rewards_release_commits_and_real_engineering_assets():
    now = datetime.now(timezone.utc)
    item = {
        "source": "github",
        "metrics": {
            "latest_release_tag": "v2.1.0",
            "latest_release_published_at": (now - timedelta(days=2)).isoformat(),
            "recent_commit_activity_checked": True,
            "recent_commit_window_days": 14,
            "recent_commit_sample_count": 8,
            "package_config_files": ["pyproject.toml"],
            "deployment_files": ["Dockerfile"],
            "test_files": ["tests/test_core.py"],
            "ci_files": [".github/workflows/test.yml"],
            "opportunity_evidence": ["原始业务证据"],
        },
    }

    profile = github_activity_profile(item, now=now)
    assert profile["score"] >= 90
    assert any("Release:v2.1.0" in value for value in profile["evidence"])
    assert any("提交样本:8" in value for value in profile["evidence"])

    attach_github_activity_metrics(item)
    evidence = item["metrics"]["opportunity_evidence"]
    assert evidence[0].startswith("GitHub工程:")
    assert "原始业务证据" in evidence


def test_github_signal_age_is_recent_but_star_velocity_uses_real_repo_age():
    now = datetime.now(timezone.utc)
    mature = {
        "source": "github",
        "created_at": (now - timedelta(days=500)).isoformat(),
        "metrics": {
            "repo_created_at": (now - timedelta(days=500)).isoformat(),
            "github_signal_at": now.isoformat(),
            "stars": 10000,
            "forks": 1000,
            "momentum": 0,
        },
    }
    truly_new = {
        "source": "github",
        "created_at": now.isoformat(),
        "metrics": {
            "repo_created_at": now.isoformat(),
            "github_signal_at": now.isoformat(),
            "stars": 10000,
            "forks": 1000,
            "momentum": 0,
        },
    }

    assert age_hours(mature) < 1
    # 两者信号都很新，但成熟仓库累计1万Star不能被当成今天获得1万Star。
    assert calculate_score(mature) < calculate_score(truly_new)


def test_build_record_preserves_repo_birth_and_separates_recent_signal_time():
    now = datetime.now(timezone.utc)
    created = (now - timedelta(days=180)).isoformat()
    pushed = (now - timedelta(hours=2)).isoformat()
    raw = {
        "id": 1,
        "name": "seller-runtime",
        "full_name": "owner/seller-runtime",
        "html_url": "https://github.com/owner/seller-runtime",
        "description": "Amazon seller workflow SDK",
        "created_at": created,
        "updated_at": pushed,
        "pushed_at": pushed,
        "stargazers_count": 800,
        "forks_count": 60,
        "open_issues_count": 5,
        "size": 500,
        "topics": ["amazon-seller", "sdk"],
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "default_branch": "main",
    }

    record = github._build_record(raw, now)
    assert record["created_at"] == created
    assert record["metrics"]["repo_created_at"] == created
    assert record["metrics"]["github_signal_at"] == pushed


def test_release_and_commit_enrichment_records_verifiable_activity(monkeypatch):
    now = datetime.now(timezone.utc)
    release_time = (now - timedelta(days=1)).isoformat()
    commit_time = (now - timedelta(hours=1)).isoformat()

    def fake_get(url, **kwargs):
        if url.endswith("/releases/latest"):
            return FakeResponse(
                payload={
                    "tag_name": "v1.4.0",
                    "name": "Stable 1.4",
                    "published_at": release_time,
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.4.0",
                }
            )
        if url.endswith("/commits"):
            return FakeResponse(
                payload=[
                    {
                        "sha": "abc123",
                        "commit": {"committer": {"date": commit_time}},
                    },
                    {
                        "sha": "def456",
                        "commit": {"committer": {"date": commit_time}},
                    },
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(github.requests, "get", fake_get)
    record = {"metrics": {}}
    assert github._enrich_latest_release(record, "owner/repo", {}) is True
    assert github._enrich_recent_commits(record, "owner/repo", "main", {}, now) is True

    metrics = record["metrics"]
    assert metrics["release_checked"] is True
    assert metrics["latest_release_tag"] == "v1.4.0"
    assert metrics["recent_commit_activity_checked"] is True
    assert metrics["recent_commit_sample_count"] == 2
    assert metrics["recent_commit_latest_sha"] == "abc123"


def test_github_card_never_displays_signal_age_as_star_daily_growth():
    value = "⭐ 20000 · Fork 1800 · +80000 星/天"
    assert _github_growth_signal(value) == "⭐ 20000 · Fork 1800"

from types import SimpleNamespace

from app import main


def _preflight(ok=True, failures=None):
    return SimpleNamespace(ok=ok, failures=list(failures or []))


def test_readiness_returns_503_when_scheduler_is_stopped(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=False))
    monkeypatch.setattr(main, "run_preflight", lambda: _preflight(True))

    response = main.readiness_check()

    assert response.status_code == 503
    assert '"就绪":false'.encode("utf-8") in response.body


def test_readiness_returns_503_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(
        main,
        "run_preflight",
        lambda: _preflight(False, ["模型密钥"]),
    )

    response = main.readiness_check()

    assert response.status_code == 503
    assert '"预检通过":false'.encode("utf-8") in response.body
    assert "模型密钥".encode("utf-8") in response.body


def test_readiness_returns_200_when_scheduler_and_preflight_are_ready(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "run_preflight", lambda: _preflight(True))

    response = main.readiness_check()

    assert response.status_code == 200
    assert '"就绪":true'.encode("utf-8") in response.body


def test_run_returns_503_when_central_pipeline_reports_preflight_failure(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_daily_radar",
        lambda: {
            "execution_id": "run-preflight",
            "status": "failed",
            "errors": ["生产预检失败：数据库"],
            "items": [],
            "policies": [],
        },
    )
    recorded = []
    monkeypatch.setattr(main, "record_run_safe", lambda result: recorded.append(result))

    response = main.run()
    assert response.status_code == 503
    assert "数据库".encode("utf-8") in response.body
    assert recorded and recorded[0]["execution_id"] == "run-preflight"


def test_runtime_status_is_lightweight(monkeypatch):
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "latest_run", lambda: {"execution_id": "run-1", "status": "success"})
    monkeypatch.setattr(main, "list_pending", lambda: ["a.json", "b.json"])
    monkeypatch.setattr(main, "list_backups", lambda: ["backup.db"])
    monkeypatch.setattr(main, "COLLECTORS", [])
    monkeypatch.setattr(main, "POLICY_COLLECTOR", SimpleNamespace(get_last_health=lambda: {}))

    result = main.runtime_status()
    assert result["调度器运行中"] is True
    assert result["最近执行"]["execution_id"] == "run-1"
    assert result["采集器状态"] == {}
    assert result["飞书待补发队列"] == 2
    assert result["数据库备份数量"] == 1


def test_runtime_status_exposes_collector_health_without_secrets(monkeypatch):
    collector = SimpleNamespace(
        name="github",
        get_last_health=lambda: {
            "source": "github",
            "success": False,
            "attempts": 2,
            "result_count": 0,
            "completed_at": "2026-08-27T02:00:00+00:00",
            "error": "ConnectionError: timeout",
        },
    )
    policy = SimpleNamespace(
        name="policy",
        get_last_health=lambda: {
            "source": "policy",
            "success": False,
            "attempts": 1,
            "result_count": 3,
            "completed_at": "2026-08-27T02:00:10+00:00",
            "error": "政策机构覆盖失败：CBP",
            "policy_sources": {
                "complete": False,
                "query_complete": False,
                "authorities_success": 4,
                "authorities_total": 5,
                "failed_authorities": ["CBP"],
                "degraded_authorities": ["Amazon"],
            },
        },
    )
    monkeypatch.setattr(main, "COLLECTORS", [collector])
    monkeypatch.setattr(main, "POLICY_COLLECTOR", policy)
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "latest_run", lambda: None)
    monkeypatch.setattr(main, "list_pending", lambda: [])
    monkeypatch.setattr(main, "list_backups", lambda: [])

    result = main.runtime_status()

    assert result["采集器状态"]["github"]["成功"] is False
    assert result["采集器状态"]["github"]["尝试次数"] == 2
    assert result["采集器状态"]["policy"]["成功"] is False
    coverage = result["采集器状态"]["policy"]["机构覆盖"]
    assert coverage["完整"] is False
    assert coverage["成功机构数"] == 4
    assert coverage["失败机构"] == ["CBP"]
    assert coverage["降级机构"] == ["Amazon"]
    assert "Webhook" not in str(result)
    assert "token" not in str(result).lower()


def test_home_uses_chinese_public_fields():
    result = main.home()

    assert result["名称"] == "AI 情报雷达"
    assert result["状态"] == "运行中"



def test_runtime_status_exposes_scheduler_plan(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class Scheduler:
        running = True

        def get_job(self, job_id):
            if job_id == "prepare_local_fallback":
                return SimpleNamespace(
                    next_run_time=datetime(
                        2026, 10, 5, 7, 35, tzinfo=ZoneInfo("Asia/Shanghai")
                    )
                )
            if job_id == "publish_daily_radar":
                return SimpleNamespace(
                    next_run_time=datetime(
                        2026, 10, 5, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")
                    )
                )
            return None

    monkeypatch.setattr(main, "scheduler", Scheduler())
    monkeypatch.setattr(main, "latest_run", lambda: None)
    monkeypatch.setattr(main, "list_pending", lambda: [])
    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "COLLECTORS", [])
    monkeypatch.setattr(main, "POLICY_COLLECTOR", SimpleNamespace(get_last_health=lambda: {}))

    result = main.runtime_status()

    assert result["调度计划"]["07:35 本地兜底"]["已注册"] is True
    assert "2026-10-05T07:35:00+08:00" == result["调度计划"]["07:35 本地兜底"]["下次执行"]
    assert result["调度计划"]["08:00 主发布"]["已注册"] is True
    assert "2026-10-05T08:00:00+08:00" == result["调度计划"]["08:00 主发布"]["下次执行"]



def test_runtime_apis_expose_deployed_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "BUILD_REVISION_FILE", tmp_path / ".missing-revision")
    monkeypatch.setenv("APP_COMMIT_SHA", "abc123def456")
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "run_preflight", lambda: _preflight(True))
    monkeypatch.setattr(main, "latest_run", lambda: None)
    monkeypatch.setattr(main, "list_pending", lambda: [])
    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "COLLECTORS", [])
    monkeypatch.setattr(main, "POLICY_COLLECTOR", SimpleNamespace(get_last_health=lambda: {}))

    assert main.home()["版本"] == "abc123def456"
    assert main.health_check()["版本"] == "abc123def456"
    assert '"版本":"abc123def456"'.encode("utf-8") in main.readiness_check().body
    assert main.runtime_status()["版本"] == "abc123def456"


def test_runtime_version_defaults_to_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "BUILD_REVISION_FILE", tmp_path / ".missing-revision")
    monkeypatch.delenv("APP_COMMIT_SHA", raising=False)
    assert main._app_version() == "unknown"


def test_baked_revision_wins_over_environment(monkeypatch, tmp_path):
    revision = tmp_path / ".build-revision"
    revision.write_text("baked-sha-123\n", encoding="utf-8")
    monkeypatch.setattr(main, "BUILD_REVISION_FILE", revision)
    monkeypatch.setenv("APP_COMMIT_SHA", "stale-env-sha")

    assert main._app_version() == "baked-sha-123"

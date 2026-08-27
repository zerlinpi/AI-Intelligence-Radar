from types import SimpleNamespace

from app import cli


def test_status_prints_collector_and_policy_coverage(monkeypatch, capsys):
    collector = SimpleNamespace(
        name="github",
        get_last_health=lambda: {
            "source": "github",
            "success": True,
            "attempts": 1,
            "result_count": 7,
            "error": "",
        },
    )
    policy = SimpleNamespace(
        name="policy",
        get_last_health=lambda: {
            "source": "policy",
            "success": False,
            "attempts": 1,
            "result_count": 2,
            "error": "政策机构覆盖失败：CBP",
            "policy_sources": {
                "authorities_success": 4,
                "authorities_total": 5,
                "failed_authorities": ["CBP"],
                "degraded_authorities": ["Amazon"],
            },
        },
    )

    monkeypatch.setattr(cli, "COLLECTORS", [collector])
    monkeypatch.setattr(cli, "POLICY_COLLECTOR", policy)
    monkeypatch.setattr(cli, "latest_run", lambda: None)
    monkeypatch.setattr(cli, "list_pending", lambda: [])
    monkeypatch.setattr(cli, "list_backups", lambda: [])

    assert cli.status() is True
    output = capsys.readouterr().out

    assert "[正常] github 尝试=1 结果=7" in output
    assert "[失败] policy 尝试=1 结果=2" in output
    assert "政策机构覆盖：4/5" in output
    assert "失败机构：CBP" in output
    assert "降级机构：Amazon" in output


def test_status_distinguishes_successful_zero_result_from_failure(monkeypatch, capsys):
    empty = SimpleNamespace(
        name="arxiv",
        get_last_health=lambda: {
            "source": "arxiv",
            "success": True,
            "attempts": 1,
            "result_count": 0,
            "error": "",
        },
    )
    monkeypatch.setattr(cli, "COLLECTORS", [empty])
    monkeypatch.setattr(cli, "POLICY_COLLECTOR", SimpleNamespace(get_last_health=lambda: {}))
    monkeypatch.setattr(cli, "latest_run", lambda: None)
    monkeypatch.setattr(cli, "list_pending", lambda: [])
    monkeypatch.setattr(cli, "list_backups", lambda: [])

    cli.status()
    output = capsys.readouterr().out

    assert "[正常] arxiv 尝试=1 结果=0" in output
    assert "[失败] arxiv" not in output

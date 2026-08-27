from app.models.radar_item import RadarItem


def test_github_activity_evidence_is_restored_after_opportunity_evidence_refresh():
    item = RadarItem(
        title="owner/repo",
        source="github",
        metrics={
            "opportunity_evidence": ["业务关键词:amazon seller"],
            "github_activity_evidence": [
                "正式Release:v2.0.0",
                "近14天提交样本:6",
                "可安装/构建:pyproject.toml",
                "可部署资产:Dockerfile",
            ],
            "deployment_readiness_reason": "具备真实代码与部署资产",
            "deployment_evidence": ["文件树:80文件/40代码文件"],
            "commercial_readiness_reason": "MIT允许商业复用",
        },
    )

    first = item.to_dict()["metrics"]["opportunity_evidence"]
    assert any(str(value).startswith("GitHub工程:") for value in first)
    assert any("正式Release:v2.0.0" in str(value) for value in first)

    # 模拟后续 relevance/scoring 刷新业务证据；独立 github_activity_evidence 不能因此丢失。
    item.metrics["opportunity_evidence"] = ["新的本地机会证据"]
    second = item.to_dict()["metrics"]["opportunity_evidence"]

    github_rows = [value for value in second if str(value).startswith("GitHub工程:")]
    assert len(github_rows) == 1
    assert "正式Release:v2.0.0" in github_rows[0]
    assert "近14天提交样本:6" in github_rows[0]
    assert "新的本地机会证据" in second
    assert any(str(value).startswith("部署成熟度:") for value in second)
    assert any(str(value).startswith("商业许可:") for value in second)

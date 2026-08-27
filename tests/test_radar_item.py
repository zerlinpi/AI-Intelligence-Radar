from app.models.radar_item import RadarItem


def test_radar_item_conversion():
    item = RadarItem(
        source="github",
        title="Test AI Project",
        url="https://example.com/project",
        description="AI project",
    )

    data = item.to_dict()

    assert data["source"] == "github"
    assert data["title"] == "Test AI Project"
    assert "metrics" in data


def test_radar_item_from_dict():
    item = RadarItem.from_dict({
        "source": "huggingface",
        "title": "Model",
        "metrics": {"downloads": 100},
    })

    assert item.source == "huggingface"
    assert item.metrics["downloads"] == 100


def test_serialization_restores_commercial_and_deployment_evidence():
    item = RadarItem(
        source="github",
        title="Seller Runtime",
        metrics={
            "opportunity_evidence": ["跨境工作流证据"],
            "commercial_readiness_reason": "MIT许可证可作为商业复用候选",
            "deployment_readiness_reason": "具备真实代码资产和近期提交",
            "deployment_evidence": ["主要语言:Python", "仓库体量:680KB", "近14天有代码提交"],
            "history_material_update_reason": "GitHub Star 显著增长：80→320",
        },
    )

    data = item.to_dict()
    evidence = data["metrics"]["opportunity_evidence"]

    assert "跨境工作流证据" in evidence
    assert any(str(value).startswith("商业许可:") for value in evidence)
    assert any(str(value).startswith("部署成熟度:") for value in evidence)
    deployment_detail = next(value for value in evidence if str(value).startswith("部署证据:"))
    assert "主要语言:Python" in deployment_detail
    assert "仓库体量:680KB" in deployment_detail
    assert any(str(value).startswith("重大更新:") for value in evidence)
    # 重大更新、许可、部署详情、部署结论会优先进入 analyzer 的前5条证据预算。
    assert any(str(value).startswith("部署证据:") for value in evidence[:5])
    # 顶层展开字段与 metrics 使用同一份已恢复的证据。
    assert data["opportunity_evidence"] == evidence


def test_serialization_does_not_mutate_original_metrics_evidence():
    item = RadarItem(
        source="huggingface",
        title="Edge Model",
        metrics={
            "opportunity_evidence": ["原始证据"],
            "deployment_readiness_reason": "具备TFLite端侧部署证据",
            "deployment_evidence": ["部署信号:tflite/int8"],
        },
    )

    first = item.to_dict()["metrics"]["opportunity_evidence"]
    second = item.to_dict()["metrics"]["opportunity_evidence"]

    assert first == second
    assert item.metrics["opportunity_evidence"] == ["原始证据"]
    assert sum(str(value).startswith("部署成熟度:") for value in first) == 1
    assert sum(str(value).startswith("部署证据:") for value in first) == 1

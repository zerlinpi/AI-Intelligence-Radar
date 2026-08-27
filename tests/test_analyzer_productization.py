from app.ai import analyzer


def test_compact_metrics_exposes_primary_lane_and_use_case_to_deepseek():
    item = {
        "source": "github",
        "metrics": {
            "primary_lane": "实体商品/硬件",
            "primary_use_case": "实体商品·安防",
            "priority_tags": ["硬件开发", "实体商品机会"],
            "product_categories": ["安防"],
            "opportunity_evidence": ["部署证据:ONNX/INT8", "camera"],
        },
    }

    compact = analyzer._compact_metrics(item)

    assert "道=实体商品/硬件" in compact
    assert "场=实体商品·安防" in compact
    assert "品=安防" in compact
    assert "据=部署证据:ONNX/INT8/camera" in compact


def test_prompt_requires_concrete_hardware_product_mvp_and_quantified_validation():
    prompt = analyzer._build_prompt("[]")

    assert "禁止只写‘可做智能硬件/摄像头/机器人’" in prompt
    assert "关键BOM模块" in prompt
    assert "2到4个最关键的" in prompt
    assert "满足什么条件才进入下一阶段" in prompt
    assert "FCC/CPSC/FDA" in prompt
    assert "不得在材料没有提供时编造具体标准号或认证结论" in prompt
    assert "代码文件、包/构建配置、测试、CI" in prompt

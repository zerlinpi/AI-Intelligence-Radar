from app.relevance import attach_eligibility_metrics, report_eligibility


def test_github_cross_border_product_is_eligible():
    result = report_eligibility(
        {
            "source": "github",
            "title": "Amazon Shopify Listing Automation",
            "description": "SDK and workflow automation for Amazon sellers and Shopify product listings",
        }
    )
    assert result["eligible"] is True
    assert result["cross_border"] is True
    assert result["evidence_sufficient"] is True


def test_generic_github_chat_demo_is_not_eligible():
    result = report_eligibility(
        {
            "source": "github",
            "title": "AI Chat Demo",
            "description": "A simple chatbot demo using an LLM",
        }
    )
    assert result["eligible"] is False


def test_github_frontier_runtime_can_be_eligible_as_developer_product():
    result = report_eligibility(
        {
            "source": "github",
            "title": "Edge Inference Runtime",
            "description": "An on-device inference runtime and compiler toolkit for embedded AI applications",
        }
    )
    assert result["eligible"] is True
    assert result["technical_frontier"] is True


def test_github_frontier_demo_template_is_not_treated_as_engineering_breakthrough():
    result = report_eligibility(
        {
            "source": "github",
            "title": "Agent Runtime Demo Template",
            "description": "Tutorial example app and starter template showing an on-device agent runtime framework",
        }
    )
    assert result["technical_frontier"] is True
    assert result["eligible"] is False
    assert "教程" in result["reason"] or "演示" in result["reason"]


def test_github_title_only_signal_is_rejected_when_evidence_is_insufficient():
    result = report_eligibility(
        {
            "source": "github",
            "title": "Amazon Seller SDK",
            "description": "AI",
        }
    )
    assert result["eligible"] is False
    assert result["evidence_sufficient"] is False
    assert "公开信息不足" in result["reason"]


def test_github_amazon_dataset_does_not_pass_as_cross_border_product():
    result = report_eligibility(
        {
            "source": "github",
            "title": "Amazon Reviews Benchmark Dataset",
            "description": (
                "A benchmark dataset of Amazon product reviews for evaluating text classification "
                "and sentiment models. It contains research data but no seller automation, SDK, app, "
                "workflow integration, listing optimizer or production tool."
            ),
        }
    )
    assert result["cross_border"] is True
    assert result["eligible"] is False
    assert "缺少可直接使用" in result["reason"]


def test_github_listing_sdk_gets_cross_border_lane_and_use_case():
    item = {
        "source": "github",
        "title": "Amazon Listing Automation SDK",
        "description": (
            "Python SDK and workflow automation for Amazon product listing optimization, keyword research, "
            "catalog localization and bulk seller operations."
        ),
        "metrics": {
            "topics": ["amazon", "ecommerce", "automation"],
            "language": "Python",
            "license_spdx": "MIT",
            "readme_evidence": True,
            "readme_chars": 1200,
        },
    }
    result = report_eligibility(item)
    assert result["eligible"] is True
    assert result["primary_lane"] == "跨境业务工具"
    assert result["primary_use_case"] == "Listing/内容"
    assert result["evidence_quality"] >= 50
    assert result["eligibility_confidence"] >= 50


def test_pure_frontier_arxiv_paper_is_not_pushed_without_business_or_physical_path():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Recursive Agent Memory for Long-Horizon Reasoning",
            "description": (
                "This paper studies recursive memory for long-horizon language-model reasoning and "
                "evaluates retrieval quality across synthetic reasoning benchmarks without describing "
                "a cross-border commerce workflow, embedded deployment path, sensor integration or "
                "consumer hardware product application."
            ),
        }
    )
    assert result["technical_frontier"] is True
    assert result["eligible"] is False


def test_arxiv_hardware_research_is_eligible_only_with_real_product_path():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "On-device Vision for Smart Pet Cameras",
            "description": (
                "We present an embedded edge AI object-detection pipeline for low-power smart pet "
                "cameras. The method quantizes a vision model for on-device inference, combines a "
                "camera with motion sensors, measures latency and memory use on embedded hardware, "
                "and demonstrates local pet-behavior detection suitable for a battery-powered consumer device."
            ),
        }
    )
    assert result["eligible"] is True
    assert result["evidence_sufficient"] is True
    assert result["hardware_enablement"] is True
    assert result["physical_product"] is True
    assert result["physical_product_path"] is True
    assert result["primary_lane"] == "实体商品/硬件"
    assert result["primary_use_case"].startswith("实体商品·")
    assert result["applied_validation"] is True
    assert "宠物用品" in result["product_categories"] or "消费电子" in result["product_categories"]


def test_arxiv_hardware_benchmark_without_product_form_is_not_eligible():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Embedded Edge Inference Benchmark",
            "description": (
                "This paper benchmarks quantized on-device neural inference on embedded processors and "
                "microcontrollers. It reports latency, memory use and energy efficiency for several models, "
                "but does not identify a consumer product form, target merchandise category, or cross-border workflow."
            ),
        }
    )
    assert result["hardware_enablement"] is True
    assert result["eligible"] is False
    assert result["physical_product_path"] is False


def test_arxiv_amazon_reviews_benchmark_without_workflow_is_not_cross_border_opportunity():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Benchmarking Language Models on Amazon Product Reviews",
            "description": (
                "We introduce a large Amazon product reviews benchmark and dataset for sentiment classification. "
                "The study compares model accuracy, calibration and robustness across review categories. "
                "It does not provide product listing optimization, seller workflow automation, inventory planning, "
                "advertising operations or another deployable ecommerce workflow."
            ),
        }
    )
    assert result["cross_border"] is True
    assert result["research_only"] is True
    assert result["eligible"] is False
    assert "工作流" in result["reason"] or "运营" in result["reason"]


def test_short_arxiv_keyword_hit_is_rejected_as_insufficient_evidence():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Edge AI Camera",
            "description": "ESP32 smart camera sensor for pet device",
        }
    )
    assert result["eligible"] is False
    assert result["evidence_sufficient"] is False


def test_generic_huggingface_text_model_is_not_eligible():
    result = report_eligibility(
        {
            "source": "huggingface",
            "title": "org/generic-text-model",
            "description": "task: text-generation | library: transformers | tags: llm text-generation",
        }
    )
    assert result["eligible"] is False


def test_huggingface_generic_edge_model_without_product_form_is_not_eligible():
    result = report_eligibility(
        {
            "source": "huggingface",
            "title": "org/edge-camera-detector",
            "description": "object detection on-device edge ai benchmark for camera sensor embedded inference",
            "metrics": {
                "pipeline_tag": "object-detection",
                "library_name": "tflite",
                "tags": ["edge-ai", "embedded", "camera"],
            },
        }
    )
    assert result["hardware_enablement"] is True
    assert result["eligible"] is False
    assert result["physical_product_path"] is False


def test_huggingface_edge_vision_model_for_security_camera_is_eligible():
    result = report_eligibility(
        {
            "source": "huggingface",
            "title": "org/edge-security-camera-detector",
            "description": (
                "object detection on-device edge ai for an embedded smart security camera consumer device "
                "with camera sensors and low-power local inference"
            ),
            "metrics": {
                "pipeline_tag": "object-detection",
                "library_name": "tflite",
                "tags": ["edge-ai", "embedded", "security-camera"],
                "model_card_evidence": True,
                "model_card_chars": 900,
            },
        }
    )
    assert result["eligible"] is True
    assert result["evidence_sufficient"] is True
    assert result["evidence_quality"] >= 50
    assert result["hardware_enablement"] is True
    assert result["physical_product_path"] is True
    assert result["primary_lane"] == "实体商品/硬件"
    assert "安防" in result["product_categories"] or "消费电子" in result["product_categories"]


def test_history_material_update_reason_is_preserved_as_deepseek_evidence():
    item = {
        "source": "github",
        "title": "acme/edge-camera",
        "description": "ESP32 edge AI camera runtime with BLE sensor integration for embedded products",
        "metrics": {
            "history_material_update": True,
            "history_material_update_reason": "GitHub Star 显著增长：80→320",
        },
    }

    result = report_eligibility(item)
    attach_eligibility_metrics(item, result)

    evidence = item["metrics"]["opportunity_evidence"]
    assert evidence
    assert evidence[0].startswith("重大更新:")
    assert "80→320" in evidence[0]
    assert item["metrics"]["physical_product_path"] is result["physical_product_path"]
    assert item["metrics"]["primary_lane"] == result["primary_lane"]
    assert item["metrics"]["primary_use_case"] == result["primary_use_case"]
    assert item["metrics"]["evidence_quality"] == result["evidence_quality"]
    assert item["metrics"]["eligibility_confidence"] == result["eligibility_confidence"]

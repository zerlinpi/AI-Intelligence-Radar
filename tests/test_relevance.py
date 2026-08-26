from app.relevance import report_eligibility


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


def test_pure_frontier_arxiv_paper_is_not_pushed_without_business_or_physical_path():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Recursive Agent Memory for Long-Horizon Reasoning",
            "description": "A new architecture for agent memory and long-horizon reasoning",
        }
    )
    assert result["technical_frontier"] is True
    assert result["eligible"] is False


def test_arxiv_hardware_research_is_eligible():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "On-device Vision for Smart Pet Cameras",
            "description": "Embedded edge AI object detection using camera sensors for a smart pet device",
        }
    )
    assert result["eligible"] is True
    assert result["hardware_enablement"] is True
    assert result["physical_product"] is True


def test_generic_huggingface_text_model_is_not_eligible():
    result = report_eligibility(
        {
            "source": "huggingface",
            "title": "org/generic-text-model",
            "description": "task: text-generation | library: transformers | tags: llm text-generation",
        }
    )
    assert result["eligible"] is False


def test_huggingface_edge_vision_model_is_eligible():
    result = report_eligibility(
        {
            "source": "huggingface",
            "title": "org/edge-camera-detector",
            "description": "object detection on-device edge ai for camera sensor embedded device",
        }
    )
    assert result["eligible"] is True
    assert result["hardware_enablement"] is True

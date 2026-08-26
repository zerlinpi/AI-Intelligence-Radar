from app.scoring import (
    business_opportunity_profile,
    calculate_priority_score,
    calculate_score,
    priority_tags,
)


def test_score_range():
    score = calculate_score({
        "stars": 10000,
        "forks": 1000,
        "comments": 500,
        "downloads": 100000,
        "upvotes": 500,
    })
    assert 0 <= score <= 100


def test_more_popular_item_scores_higher():
    low = calculate_score({"stars": 10})
    high = calculate_score({"stars": 10000})
    assert high > low


def test_cross_border_ecommerce_project_gets_strong_opportunity_priority():
    item = {
        "title": "AI Shopify Listing Copilot",
        "description": "Automates Amazon and Shopify product listing optimization",
        "source": "github",
    }
    tags = priority_tags(item)
    assert "跨境电商" in tags
    assert "可产品化" in tags
    assert calculate_priority_score(item) >= 50


def test_frontier_agent_memory_research_is_not_discarded_as_generic_research():
    item = {
        "title": "Recursive Agent Memory for Long-Horizon Reasoning",
        "description": "A novel architecture for long-term memory and tool use in autonomous agents",
        "source": "arxiv",
    }
    profile = business_opportunity_profile(item)
    assert "技术前沿" in profile["tags"]
    assert profile["dimensions"]["technical_frontier"] >= 10
    assert profile["opportunity_score"] >= 20


def test_hardware_ai_project_gets_hardware_physical_category_and_evidence_signals():
    item = {
        "title": "ESP32 Edge AI Pet Camera",
        "description": (
            "On-device computer vision for an ESP32 smart pet camera with BLE, "
            "sensor input and embedded firmware"
        ),
        "source": "github",
        "metrics": {},
    }
    profile = business_opportunity_profile(item)
    assert "硬件开发" in profile["tags"]
    assert "实体商品机会" in profile["tags"]
    assert "宠物用品" in profile["product_categories"]
    assert "商品·宠物用品" in profile["tags"]
    assert profile["evidence"]
    assert any(tag.startswith("证据·") for tag in profile["tags"])
    assert profile["dimensions"]["hardware_enablement"] >= 10
    assert profile["dimensions"]["physical_product"] >= 8

    # pipeline 先调用 priority_tags / calculate_priority_score；画像应同步写回 metrics，
    # 以便 DeepSeek 在二次分析时看到本地筛选依据。
    priority_tags(item)
    calculate_priority_score(item)
    assert item["metrics"]["product_categories"]
    assert item["metrics"]["opportunity_evidence"]
    assert item["metrics"]["opportunity_dimensions"]["hardware_enablement"] >= 10


def test_health_mobility_hardware_maps_to_health_assistive_category():
    item = {
        "title": "On-device vision controller for smart wheelchair mobility aid",
        "description": "Embedded sensor and camera system for wheelchair mobility assistance",
        "source": "github",
    }
    profile = business_opportunity_profile(item)
    assert "硬件开发" in profile["tags"]
    assert "实体商品机会" in profile["tags"]
    assert "健康辅助" in profile["product_categories"]


def test_plain_software_tool_does_not_become_physical_tool_product():
    item = {
        "title": "AI Monitoring Tool",
        "description": "Cloud SaaS dashboard and API for monitoring LLM application logs",
        "source": "github",
    }
    profile = business_opportunity_profile(item)
    assert "实体商品机会" not in profile["tags"]
    assert "商品·工具DIY" not in profile["tags"]
    assert profile["product_categories"] == []


def test_plain_theoretical_research_without_application_signal_stays_low_priority():
    item = {
        "title": "Abstract Optimization Bounds",
        "description": "A theoretical proof about asymptotic optimization bounds",
        "source": "arxiv",
    }
    profile = business_opportunity_profile(item)
    assert "跨境电商" not in profile["tags"]
    assert "硬件开发" not in profile["tags"]
    assert "实体商品机会" not in profile["tags"]
    assert profile["opportunity_score"] < 20

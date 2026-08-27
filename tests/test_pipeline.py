from contextlib import contextmanager
from datetime import datetime, timezone

from app import pipeline
from app.cards.models import ComplianceDecision, ProductDecision
from app.models.radar_item import RadarItem
from app.pipeline import build_report


def _analysis_for(items, score=82, opportunity="high"):
    return [
        {
            "purpose": "项目具有明确的可执行能力和目标使用场景。",
            "summary": "该能力可进入实际业务或产品开发流程，但仍需验证真实效果。",
            "business_score": score,
            "opportunity": opportunity,
            "startup_ideas": ["先做小范围原型并验证核心指标"],
            "llm_meta": {"success": True, "fallback": False},
        }
        for _ in items
    ]


def test_build_report_returns_only_quality_items(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(pipeline, "analyze_items", lambda items: _analysis_for(items))

    items = [
        {
            "title": "Generic Chat Demo",
            "source": "github",
            "description": "A simple generic AI chat demo",
            "created_at": now,
            "stars": 1000,
        },
        {
            "title": "Amazon Listing Workflow SDK",
            "source": "github",
            "description": "Reusable SDK and automation workflow for Amazon sellers to optimize listings and localization",
            "created_at": now,
            "stars": 20,
        },
    ]

    result = build_report(items)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].title == "Amazon Listing Workflow SDK"
    assert all(isinstance(item, RadarItem) for item in result)


def test_build_report_adds_analysis(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(pipeline, "analyze_items", lambda items: _analysis_for(items))

    items = [
        {
            "title": "Seller Listing SDK",
            "source": "github",
            "url": "https://example.com",
            "description": "SDK and workflow automation for Amazon seller listings, localization and keyword optimization",
            "created_at": now,
            "stars": 100,
        }
    ]

    result = build_report(items)

    assert len(result) == 1
    assert isinstance(result[0].analysis, dict)
    assert result[0].analysis
    assert result[0].metrics["final_report_eligible"] is True


def test_cross_border_product_is_prioritized(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(pipeline, "analyze_items", lambda items: _analysis_for(items))

    items = [
        {
            "title": "General AI Research",
            "description": "A new neural network research project without a reusable product path",
            "source": "github",
            "created_at": now,
            "stars": 100,
        },
        {
            "title": "Shopify Listing Copilot",
            "description": "AI SDK for Amazon and Shopify product listings, keyword localization and seller workflow automation",
            "source": "github",
            "created_at": now,
            "stars": 20,
        },
    ]

    result = build_report(items)

    assert result[0].title == "Shopify Listing Copilot"
    assert "跨境电商" in result[0].metrics["priority_tags"]
    assert "可产品化" in result[0].metrics["priority_tags"]
    assert result[0].metrics["priority_score"] >= 50


def test_hardware_product_can_outrank_hot_but_generic_project(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(pipeline, "analyze_items", lambda items: _analysis_for(items))

    items = [
        {
            "title": "Generic Chat Demo",
            "description": "Simple AI chat demo with no reusable product capability",
            "source": "github",
            "created_at": now,
            "stars": 500,
        },
        {
            "title": "ESP32 Edge AI Camera",
            "description": "Embedded on-device computer vision runtime with BLE sensors for a smart home camera hardware prototype",
            "source": "github",
            "created_at": now,
            "stars": 30,
        },
    ]

    result = build_report(items)
    assert result[0].title == "ESP32 Edge AI Camera"
    assert "硬件开发" in result[0].metrics["priority_tags"]
    assert "实体商品机会" in result[0].metrics["priority_tags"]


def test_strategic_portfolio_preserves_quality_without_forcing_ten_items():
    now = datetime.now(timezone.utc).isoformat()
    items = []

    for index in range(10):
        items.append(
            {
                "title": f"Generic AI Chat {index}",
                "description": "Simple AI chat application with no reusable commerce or hardware path",
                "source": "github",
                "created_at": now,
                "stars": 500 - index,
            }
        )

    items.extend(
        [
            {
                "title": "Amazon Shopify Listing Intelligence",
                "description": "Amazon seller and Shopify listing optimization with product research, localization and workflow automation",
                "source": "producthunt",
                "created_at": now,
                "upvotes": 40,
            },
            {
                "title": "ESP32 Edge Vision Runtime",
                "description": "Embedded edge AI runtime with ESP32 camera, BLE sensor integration and firmware for consumer device prototypes",
                "source": "huggingface",
                "created_at": now,
                "downloads": 200,
                "metrics": {
                    "pipeline_tag": "object-detection",
                    "library_name": "tflite",
                    "tags": ["edge-ai", "embedded", "camera"],
                },
            },
            {
                "title": "Smart Pet Camera Prototype",
                "description": "On-device computer vision smart pet camera with embedded sensor, BLE and local inference firmware",
                "source": "github",
                "created_at": now,
                "stars": 30,
            },
        ]
    )

    result = pipeline.select_project_candidates(items)
    titles = {item.title for item in result}
    tags = {
        tag
        for item in result
        for tag in ((item.metrics or {}).get("priority_tags") or [])
    }

    assert "Amazon Shopify Listing Intelligence" in titles
    assert "ESP32 Edge Vision Runtime" in titles
    assert "Smart Pet Camera Prototype" in titles
    assert all(not title.startswith("Generic AI Chat") for title in titles)
    assert "跨境电商" in tags
    assert "技术前沿" in tags
    assert "硬件开发" in tags
    assert "实体商品机会" in tags
    assert 1 <= len(result) < pipeline.MAX_REPORT_ITEMS


def test_pre_llm_homogeneous_use_case_does_not_fill_daily_token_budget():
    now = datetime.now(timezone.utc).isoformat()
    items = [
        {
            "title": f"GitHub Commerce Automation SDK {index}",
            "description": "Reusable Amazon seller API framework and workflow automation SDK for product listing localization and ecommerce operations",
            "source": "github",
            "created_at": now,
            "stars": 100 - index,
        }
        for index in range(12)
    ]

    result = pipeline.select_project_candidates(items)

    assert 1 <= len(result) <= pipeline.PRE_LLM_MAX_PER_USE_CASE
    assert len(result) < pipeline.MAX_REPORT_ITEMS
    assert all(
        (item.metrics or {}).get("primary_use_case") == "Listing/内容"
        for item in result
    )


def test_pre_llm_portfolio_backfills_other_use_cases_instead_of_more_listing_agents():
    now = datetime.now(timezone.utc).isoformat()
    items = [
        {
            "title": f"Listing Agent {index}",
            "description": "Amazon seller product listing localization and SEO workflow automation SDK with API integration",
            "source": "github",
            "created_at": now,
            "stars": 120 - index,
        }
        for index in range(8)
    ]
    items.extend(
        [
            {
                "title": "Competitor Research SDK",
                "description": "Amazon seller product research competitor research sourcing workflow automation SDK with API integration",
                "source": "github",
                "created_at": now,
                "stars": 60,
            },
            {
                "title": "Ad Creative Workflow SDK",
                "description": "Amazon seller advertising ad creative influencer workflow automation SDK with API integration",
                "source": "github",
                "created_at": now,
                "stars": 58,
            },
            {
                "title": "Inventory Operations SDK",
                "description": "Amazon seller inventory fulfillment logistics warehouse workflow automation SDK with API integration",
                "source": "github",
                "created_at": now,
                "stars": 56,
            },
            {
                "title": "Review Support SDK",
                "description": "Amazon seller customer support review analysis workflow automation SDK with API integration",
                "source": "github",
                "created_at": now,
                "stars": 54,
            },
        ]
    )

    result = pipeline.select_project_candidates(items)
    use_cases = [str((item.metrics or {}).get("primary_use_case") or "") for item in result]

    assert use_cases.count("Listing/内容") <= pipeline.PRE_LLM_MAX_PER_USE_CASE
    assert "选品/竞品" in use_cases
    assert "广告/增长" in use_cases
    assert "库存/履约" in use_cases
    assert "客服/评论" in use_cases


def test_source_cap_remains_soft_when_same_source_has_different_use_cases():
    now = datetime.now(timezone.utc).isoformat()
    descriptions = [
        ("Listing SDK", "Amazon seller product listing localization SEO workflow automation SDK API"),
        ("Research SDK", "Amazon seller product research competitor research sourcing workflow automation SDK API"),
        ("Ads SDK", "Amazon seller advertising ad creative influencer workflow automation SDK API"),
        ("Inventory SDK", "Amazon seller inventory fulfillment logistics warehouse workflow automation SDK API"),
        ("Support SDK", "Amazon seller customer support review analysis workflow automation SDK API"),
        ("Pricing SDK", "Amazon seller pricing price tracking workflow automation SDK API"),
        ("Edge Runtime", "On-device edge AI inference runtime compiler quantization framework SDK for embedded deployment"),
    ]
    items = [
        {
            "title": title,
            "description": description,
            "source": "github",
            "created_at": now,
            "stars": 100 - index,
        }
        for index, (title, description) in enumerate(descriptions)
    ]

    result = pipeline.select_project_candidates(items)

    assert len(result) == 7
    assert all(item.source == "github" for item in result)
    assert len({(item.metrics or {}).get("primary_use_case") for item in result}) >= 7


def test_summary_actions_reference_detail_cards_instead_of_repeating_body_copy():
    policy_action = "立即整理CPC、测试报告和eFiling字段并完成适用范围核对。"
    product_action = "先在ESP32样机验证延迟、RAM、功耗和识别准确率。"
    compliance = [
        ComplianceDecision(
            focus="产品合规审核",
            title="CPSC eFiling 新要求",
            source_name="CPSC",
            authority="CPSC",
            risk_level="high",
            impact_score=95,
            requirement="进口受监管消费品需要电子申报合规证书。",
            preparation="准备CPC、测试报告和eFiling字段。",
            action=policy_action,
        )
    ]
    products = [
        ProductDecision(
            title="ESP32 Edge Camera",
            source_name="GitHub",
            business_score=90,
            opportunity="high",
            direction=product_action,
        )
    ]

    actions = pipeline._build_summary_actions(compliance, products)

    assert actions[0].text != policy_action
    assert "见合规卡" in actions[0].text
    assert actions[2].text != product_action
    assert "见产品机会卡" in actions[2].text


def test_deepseek_final_gate_rejects_low_value_analysis(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()

    def analyze(items):
        rows = []
        for item in items:
            if "Weak" in item["title"]:
                rows.extend(_analysis_for([item], score=54, opportunity="low"))
            else:
                rows.extend(_analysis_for([item], score=84, opportunity="high"))
        return rows

    monkeypatch.setattr(pipeline, "analyze_items", analyze)
    items = [
        {
            "title": "Strong Amazon Seller SDK",
            "description": "Amazon seller API and automation SDK for listing localization, inventory and ecommerce workflow integration",
            "source": "github",
            "created_at": now,
            "stars": 25,
        },
        {
            "title": "Weak Amazon Seller SDK",
            "description": "Amazon seller API and automation SDK for listing localization with an otherwise limited product implementation",
            "source": "github",
            "created_at": now,
            "stars": 24,
        },
    ]

    result = build_report(items)
    assert [item.title for item in result] == ["Strong Amazon Seller SDK"]


def test_run_daily_radar_skips_when_another_execution_is_running(monkeypatch):
    @contextmanager
    def locked():
        yield False

    monkeypatch.setattr(pipeline, "execution_lock", locked)

    result = pipeline.run_daily_radar()

    assert result["skipped"] is True
    assert result["reason"] == "已有任务正在运行"
    assert result["items"] == []
from app.cards import build_daily_cards
from app.cards.models import DailySummary, ProductDecision, ReportDecisionModel
from app.product_portfolio import compress_product_portfolio, product_use_case
from app.source_coverage import reset_collection_health


def _product(
    title,
    description,
    *,
    age="12小时前",
    business=80,
    opportunity="medium",
    tags=None,
    cross_border=True,
):
    return ProductDecision(
        title=title,
        source_name="GitHub",
        age_text=age,
        url=f"https://example.com/{title.replace(' ', '-').lower()}",
        trend_score=70,
        business_score=business,
        opportunity=opportunity,
        tags=list(tags or (["跨境电商", "可产品化"] if cross_border else ["可产品化"])),
        description=description,
        growth_signal="测试增长信号",
        judgment="该项目具有明确的实际使用价值，但仍需在真实业务中验证稳定性和成本。",
        direction="先用真实SKU或硬件原型做小规模验证，再根据结果决定是否进入正式开发。",
        cross_border=cross_border,
    )


def test_same_listing_use_case_keeps_primary_and_best_fresh_alternative():
    primary = _product(
        "Listing Leader",
        "Amazon listing optimization tool",
        age="4天前",
        business=91,
    )
    older = _product(
        "Listing Older",
        "Amazon listing localization tool",
        age="8天前",
        business=86,
    )
    fresh = _product(
        "Listing Fresh",
        "Amazon listing content generator",
        age="8小时前",
        business=82,
    )
    weak = _product(
        "Listing Weak",
        "Amazon listing SEO assistant",
        age="1天前",
        business=70,
    )

    selected, stats = compress_product_portfolio([primary, older, fresh, weak])

    assert [item.title for item in selected] == ["Listing Leader", "Listing Fresh"]
    assert stats["suppressed"] == 2
    assert stats["use_cases"] == {"Listing/内容": 2}


def test_exceptional_same_use_case_can_keep_one_extra_item():
    products = [
        _product(
            f"Listing Exceptional {index}",
            "Amazon listing optimization and localization",
            business=95 - index,
            opportunity="high",
        )
        for index in range(3)
    ]

    selected, stats = compress_product_portfolio(products)

    assert len(selected) == 3
    assert stats["suppressed"] == 0


def test_different_physical_product_categories_are_not_collapsed():
    pet = _product(
        "Edge Pet Camera",
        "ESP32 edge AI camera with BLE sensor for pet behavior recognition",
        tags=["硬件开发", "实体商品机会", "商品·宠物用品"],
        cross_border=False,
    )
    auto = _product(
        "Vehicle Vision Sensor",
        "Embedded computer vision sensor for vehicle monitoring",
        tags=["硬件开发", "实体商品机会", "商品·汽车出行"],
        cross_border=False,
    )

    assert product_use_case(pet) == "实体商品·宠物用品"
    assert product_use_case(auto) == "实体商品·汽车出行"

    selected, _ = compress_product_portfolio([pet, auto])
    assert [item.title for item in selected] == [pet.title, auto.title]


def test_edge_runtime_is_not_collapsed_into_real_hardware_prototype():
    runtime = _product(
        "Edge AI Runtime",
        "On-device inference runtime with quantization and low-memory execution",
        tags=["技术前沿", "可产品化"],
        cross_border=False,
    )
    camera = _product(
        "Pet Camera Hardware",
        "ESP32 camera with BLE sensor and on-device recognition",
        tags=["硬件开发", "实体商品机会", "商品·宠物用品"],
        cross_border=False,
    )

    assert product_use_case(runtime) == "开发基础设施·端侧/推理"
    assert product_use_case(camera) == "实体商品·宠物用品"

    selected, _ = compress_product_portfolio([runtime, camera])
    assert [item.title for item in selected] == [runtime.title, camera.title]


def test_one_cross_border_lane_cannot_fill_entire_report():
    products = [
        _product("Listing Tool", "Amazon listing optimization"),
        _product("Research Tool", "Amazon product research and competitor research"),
        _product("Ads Tool", "Amazon advertising and ad creative automation"),
        _product("Inventory Tool", "Amazon inventory and fulfillment planning"),
        _product("Support Tool", "Amazon customer support and review analysis"),
        _product("Pricing Tool", "Amazon pricing and repricing automation"),
    ]

    selected, stats = compress_product_portfolio(products)

    assert len(selected) == 4
    assert stats["lanes"] == {"跨境业务工具": 4}
    assert stats["suppressed"] == 2


def test_card_entry_applies_portfolio_and_updates_summary_metrics():
    reset_collection_health()
    products = [
        _product(
            f"Listing Product {index}",
            "Amazon listing optimization and localization",
            business=90 - index,
            age=f"{index + 1}小时前",
        )
        for index in range(5)
    ]
    model = ReportDecisionModel(
        summary=DailySummary(
            date_text="08月27日",
            judgment="产品侧优先研究 Listing Product 0。",
            actions=[],
            metrics={
                "compliance": 0,
                "high_risk": 0,
                "projects": 5,
                "opportunities": 5,
            },
        ),
        compliance=[],
        products=products,
    )

    cards = build_daily_cards(model)

    assert len(model.products) == 2
    assert model.products[0].title == "Listing Product 0"
    assert model.summary.metrics["projects"] == 2
    assert model.summary.metrics["portfolio_input"] == 5
    assert model.summary.metrics["portfolio_suppressed"] == 3
    rendered = "\n".join(str(card.payload) for card in cards)
    assert "Listing Product 0" in rendered
    assert "Listing Product 1" in rendered
    assert "Listing Product 4" not in rendered
    reset_collection_health()

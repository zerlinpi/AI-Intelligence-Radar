from app.cards.builders import build_product_cards
from app.cards.models import DailySummary, ProductDecision, ReportDecisionModel


def _model(products):
    return ReportDecisionModel(
        summary=DailySummary(
            date_text="08月26日",
            judgment="测试",
            metrics={"projects": len(products)},
        ),
        products=products,
    )


def _serialized(cards):
    return "\n".join(str(card.payload) for card in cards)


def test_product_cards_split_cross_border_hardware_frontier_and_other_groups():
    products = [
        ProductDecision(
            title="Amazon Listing Agent",
            source_name="GitHub",
            age_text="8小时前",
            cross_border=True,
            tags=["跨境电商", "可产品化"],
            description="Listing automation",
            direction="开发卖家插件",
        ),
        ProductDecision(
            title="ESP32 Pet Camera",
            source_name="GitHub",
            age_text="6小时前",
            tags=[
                "硬件开发",
                "实体商品机会",
                "商品·宠物用品",
                "证据·esp32/edge ai/pet camera",
                "可产品化",
            ],
            description="Edge AI pet camera",
            direction="做端侧识别宠物摄像头原型",
        ),
        ProductDecision(
            title="Recursive Agent Memory",
            source_name="arXiv",
            age_text="12小时前",
            tags=["技术前沿", "可产品化"],
            description="Long horizon memory architecture",
            direction="复现并验证长任务可靠性",
        ),
        ProductDecision(
            title="Generic API Tool",
            source_name="Product Hunt",
            age_text="1天前",
            tags=["可产品化"],
            description="Generic API",
            direction="验证需求",
        ),
    ]

    serialized = _serialized(build_product_cards(_model(products), max_projects=5))

    assert "🎯 跨境电商直接相关" in serialized
    assert "🧰 硬件与实体商品机会" in serialized
    assert "🧠 技术前沿与开发基础设施" in serialized
    assert "🧪 其他可产品化信号" in serialized
    assert "商品·宠物用品" in serialized
    assert "证据·esp32/edge ai/pet camera" in serialized
    assert "落地动作" in serialized
    assert "原型验证" in serialized
    assert "产品化验证" in serialized
    assert "下一步" in serialized
    assert "1项" in serialized


def test_project_is_not_duplicated_across_multiple_value_groups():
    project = ProductDecision(
        title="Cross-border Smart Camera",
        source_name="GitHub",
        age_text="3小时前",
        cross_border=True,
        tags=["跨境电商", "硬件开发", "实体商品机会", "可产品化"],
        description="Smart camera for marketplace sellers",
        direction="开发商品原型",
    )

    serialized = _serialized(build_product_cards(_model([project]), max_projects=5))
    assert serialized.count("Cross-border Smart Camera") == 1
    assert "🎯 跨境电商直接相关" in serialized
    assert "🧰 硬件与实体商品机会" not in serialized

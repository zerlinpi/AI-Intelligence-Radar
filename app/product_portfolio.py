import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

from app.cards.models import ProductDecision


# 这里只压缩“已经通过本地 Gate + DeepSeek 最终 Gate”的项目组合，
# 不重新判断项目真假，也不会把被压缩的条目从历史数据库删除。
DEFAULT_MAX_ITEMS = 10
DEFAULT_MAX_PER_USE_CASE = 2
DEFAULT_MAX_PER_LANE = 4
EXCEPTIONAL_BUSINESS_SCORE = 92


_USE_CASE_SIGNALS = (
    (
        "Listing/内容",
        (
            "listing", "bullet point", "a+ content", "localization", "seo",
            "商品标题", "卖点", "本地化", "listing优化", "内容生成",
        ),
    ),
    (
        "选品/竞品",
        (
            "product research", "competitor research", "keyword research", "sourcing",
            "选品", "竞品", "关键词研究", "采购", "供应商",
        ),
    ),
    (
        "广告/增长",
        (
            "advertising", "ad creative", "meta ads", "google ads", "affiliate",
            "influencer", "ugc", "广告", "达人", "广告素材", "投放",
        ),
    ),
    (
        "库存/履约",
        (
            "inventory", "fulfillment", "logistics", "warehouse", "shipping", "returns",
            "库存", "履约", "物流", "仓储", "运输", "退货",
        ),
    ),
    (
        "客服/评论",
        (
            "customer support", "customer service", "review analysis", "reviews",
            "客服", "评论分析", "评论", "售后",
        ),
    ),
    (
        "定价",
        ("pricing", "price tracking", "repricing", "定价", "价格跟踪", "调价"),
    ),
)

_INFRA_SIGNALS = (
    ("开发基础设施·端侧/推理", ("edge ai", "on-device", "runtime", "inference", "quantization", "端侧", "推理", "量化")),
    ("开发基础设施·视觉/机器人", ("computer vision", "robotics", "slam", "robot", "视觉", "机器人")),
    ("开发基础设施·Agent", ("agent memory", "multi-agent", "agentic", "tool use", "agent", "智能体")),
    ("开发基础设施·SDK/API", ("sdk", "api", "framework", "library", "toolkit", "compiler", "开发框架", "编译器")),
)

_HARDWARE_SIGNALS = (
    "esp32", "mcu", "embedded", "firmware", "sensor", "camera", "ble", "iot",
    "edge ai", "on-device", "robotics", "motor control",
    "嵌入式", "固件", "传感器", "摄像头", "端侧", "机器人", "电机控制",
)


def _normalized_text(product: ProductDecision) -> str:
    parts = [
        product.title,
        product.description,
        product.judgment,
        product.direction,
        " ".join(product.tags or []),
    ]
    return " ".join(str(part or "").lower() for part in parts)


def _contains(text: str, signal: str) -> bool:
    signal = str(signal or "").lower().strip()
    if not signal:
        return False
    if re.fullmatch(r"[a-z0-9+.-]+", signal):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])", text))
    return signal in text


def _first_product_category(tags: Iterable[str]) -> str:
    for raw in tags or []:
        tag = str(raw or "").strip()
        if tag.startswith("商品·") and len(tag) > len("商品·"):
            return tag.split("·", 1)[1]
    return ""


def product_lane(product: ProductDecision) -> str:
    tags = set(str(tag or "").strip() for tag in (product.tags or []))
    if product.cross_border:
        return "跨境业务工具"
    if "硬件开发" in tags or "实体商品机会" in tags:
        return "实体商品/硬件"
    if "技术前沿" in tags:
        return "开发基础设施"
    return "其他"


def product_use_case(product: ProductDecision) -> str:
    text = _normalized_text(product)

    # 跨境业务场景优先细分，避免多个 Listing/选品/广告工具重复占位。
    for label, signals in _USE_CASE_SIGNALS:
        if any(_contains(text, signal) for signal in signals):
            return label

    tags = list(product.tags or [])
    category = _first_product_category(tags)
    if category:
        return f"实体商品·{category}"

    if any(_contains(text, signal) for signal in _HARDWARE_SIGNALS):
        return "实体商品·硬件原型"

    for label, signals in _INFRA_SIGNALS:
        if any(_contains(text, signal) for signal in signals):
            return label

    return "其他"


def _age_hours(age_text: str):
    value = str(age_text or "").strip()
    if not value or value == "时间未知":
        return None
    if "1小时内" in value:
        return 0.5

    match = re.search(r"(\d+)\s*小时前", value)
    if match:
        return float(match.group(1))

    match = re.search(r"(\d+)\s*天前", value)
    if match:
        return float(match.group(1)) * 24
    return None


def _freshness_bonus(product: ProductDecision) -> float:
    hours = _age_hours(product.age_text)
    if hours is None:
        return 0.0
    if hours <= 24:
        return 10.0
    if hours <= 72:
        return 7.0
    if hours <= 168:
        return 3.0
    return 0.0


def _portfolio_score(product: ProductDecision) -> float:
    business = max(min(float(product.business_score or 0), 100), 0)
    opportunity_bonus = 5.0 if str(product.opportunity).lower() == "high" else 0.0
    return business + opportunity_bonus + _freshness_bonus(product)


def _is_exceptional(product: ProductDecision) -> bool:
    return (
        str(product.opportunity or "").lower() == "high"
        and float(product.business_score or 0) >= EXCEPTIONAL_BUSINESS_SCORE
    )


def compress_product_portfolio(
    products: List[ProductDecision],
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_per_use_case: int = DEFAULT_MAX_PER_USE_CASE,
    max_per_lane: int = DEFAULT_MAX_PER_LANE,
) -> Tuple[List[ProductDecision], Dict]:
    """压缩最终飞书产品组合，优先保留同场景中“价值更高且更新”的代表项目。

    输入顺序通常已经是主流程最终效用排序。这里不会引入低价值候选，只在已经合格的
    项目之间做同场景去重。被压缩项目仍保留在数据库历史中，因此不会在下一轮重复消耗 LLM。
    """
    products = list(products or [])
    if not products:
        return [], {
            "input": 0,
            "selected": 0,
            "suppressed": 0,
            "use_cases": {},
            "lanes": {},
        }

    original_index = {id(product): index for index, product in enumerate(products)}
    grouped = defaultdict(list)
    for product in products:
        grouped[product_use_case(product)].append(product)

    use_case_candidates = []
    use_case_suppressed = 0
    for use_case, group in grouped.items():
        ranked = sorted(
            group,
            key=lambda product: (
                _portfolio_score(product),
                float(product.business_score or 0),
                -original_index[id(product)],
            ),
            reverse=True,
        )

        keep_limit = max_per_use_case
        exceptional = [product for product in ranked if _is_exceptional(product)]
        if len(exceptional) > max_per_use_case:
            # 同场景极高价值项目允许最多再保留一条，但仍阻止一类内容占满日报。
            keep_limit = max_per_use_case + 1

        kept = ranked[:keep_limit]
        use_case_candidates.extend(kept)
        use_case_suppressed += max(len(group) - len(kept), 0)

    # 恢复主流程效用排序，再限制同一大方向占比。
    use_case_candidates.sort(key=lambda product: original_index[id(product)])
    selected = []
    lane_counts = Counter()
    lane_exception_used = Counter()
    lane_suppressed = 0

    for product in use_case_candidates:
        if len(selected) >= max_items:
            lane_suppressed += 1
            continue

        lane = product_lane(product)
        if lane_counts[lane] >= max_per_lane:
            # 极高价值项目可突破大方向上限 1 次，避免机械删掉真正重要的机会。
            if not _is_exceptional(product) or lane_exception_used[lane] >= 1:
                lane_suppressed += 1
                continue
            lane_exception_used[lane] += 1

        selected.append(product)
        lane_counts[lane] += 1

    use_case_counts = Counter(product_use_case(product) for product in selected)
    return selected, {
        "input": len(products),
        "selected": len(selected),
        "suppressed": len(products) - len(selected),
        "use_case_suppressed": use_case_suppressed,
        "lane_suppressed": lane_suppressed,
        "use_cases": dict(use_case_counts),
        "lanes": dict(lane_counts),
    }

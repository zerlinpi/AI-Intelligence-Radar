import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

from app.cards.models import ProductDecision
from app.content_quality import copy_similarity


# 这里只压缩“已经通过本地 Gate + DeepSeek 最终 Gate”的项目组合，
# 不重新判断项目真假，也不会把被压缩的条目从历史数据库删除。
DEFAULT_MAX_ITEMS = 10
DEFAULT_MAX_PER_USE_CASE = 2
DEFAULT_MAX_PER_LANE = 4
EXCEPTIONAL_BUSINESS_SCORE = 92

# “同一个使用场景”不代表一定要保留两条。若能力说明和最终分析高度相似，
# 只保留主流程已经排在前面的代表项目，避免飞书出现换名字但内容基本相同的机会。
SEMANTIC_DESCRIPTION_THRESHOLD = 0.84
SEMANTIC_SUPPORT_DESCRIPTION_THRESHOLD = 0.72
SEMANTIC_ANALYSIS_THRESHOLD = 0.88
SEMANTIC_MIN_DESCRIPTION_CHARS = 24
SEMANTIC_MIN_ANALYSIS_CHARS = 36


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
    tags = list(product.tags or [])
    tag_set = set(str(tag or "").strip() for tag in tags)

    # 跨境业务场景优先细分，避免多个 Listing/选品/广告工具重复占位。
    for label, signals in _USE_CASE_SIGNALS:
        if any(_contains(text, signal) for signal in signals):
            return label

    # 已经识别出的具体实体商品品类优先于泛化的 edge AI / vision 等技术词。
    category = _first_product_category(tags)
    if category:
        return f"实体商品·{category}"

    # “技术前沿”但没有硬件/实体商品标签时，优先理解为开发基础设施。
    # 这样 Edge AI Runtime 不会和真正的摄像头/传感器硬件原型误归为一类。
    if "技术前沿" in tag_set and not ({"硬件开发", "实体商品机会"} & tag_set):
        for label, signals in _INFRA_SIGNALS:
            if any(_contains(text, signal) for signal in signals):
                return label

    if ({"硬件开发", "实体商品机会"} & tag_set) or any(
        _contains(text, signal) for signal in _HARDWARE_SIGNALS
    ):
        return "实体商品·硬件原型"

    for label, signals in _INFRA_SIGNALS:
        if any(_contains(text, signal) for signal in signals):
            return label

    return "其他"


def _semantic_description(product: ProductDecision) -> str:
    return " ".join(str(product.description or "").split()).strip()


def _semantic_analysis(product: ProductDecision) -> str:
    return " ".join(
        part
        for part in (
            " ".join(str(product.judgment or "").split()).strip(),
            " ".join(str(product.direction or "").split()).strip(),
        )
        if part
    ).strip()


def _same_semantic_opportunity(left: ProductDecision, right: ProductDecision) -> bool:
    """判断同一使用场景里的两条机会是否只是在重复表达同一种能力。

    标题、标签和热度不参与判重，避免同一技术被不同项目名称包装后绕过压缩；
    同时要求有足够正文证据，短描述不会仅凭几个相同关键词被误删。
    """
    left_description = _semantic_description(left)
    right_description = _semantic_description(right)
    if (
        min(len(left_description), len(right_description))
        < SEMANTIC_MIN_DESCRIPTION_CHARS
    ):
        return False

    description_similarity = copy_similarity(left_description, right_description)
    if description_similarity >= SEMANTIC_DESCRIPTION_THRESHOLD:
        return True

    left_analysis = _semantic_analysis(left)
    right_analysis = _semantic_analysis(right)
    if min(len(left_analysis), len(right_analysis)) < SEMANTIC_MIN_ANALYSIS_CHARS:
        return False

    analysis_similarity = copy_similarity(left_analysis, right_analysis)
    return (
        description_similarity >= SEMANTIC_SUPPORT_DESCRIPTION_THRESHOLD
        and analysis_similarity >= SEMANTIC_ANALYSIS_THRESHOLD
    )


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
    """压缩最终飞书产品组合，优先保留同场景中真正不同的高价值机会。

    输入顺序通常已经是主流程最终效用排序。这里不会引入低价值候选；先在同一使用场景
    内删除功能/判断/方向高度相似的机会，再执行场景和大方向配额。被压缩项目仍保留在
    数据库历史中，因此不会在下一轮重复消耗 LLM。
    """
    products = list(products or [])
    if not products:
        return [], {
            "input": 0,
            "selected": 0,
            "suppressed": 0,
            "semantic_suppressed": 0,
            "use_cases": {},
            "lanes": {},
        }

    original_index = {id(product): index for index, product in enumerate(products)}
    grouped = defaultdict(list)
    for product in products:
        grouped[product_use_case(product)].append(product)

    use_case_candidates = []
    use_case_suppressed = 0
    semantic_suppressed = 0
    for use_case, group in grouped.items():
        # 主流程顺序已经融合最终价值、证据和时间，固定保留排在最前面的代表，
        # 同时避免组合压缩后摘要仍引用被删除项目。
        primary = min(group, key=lambda product: original_index[id(product)])
        ranked_others = sorted(
            [product for product in group if product is not primary],
            key=lambda product: (
                _portfolio_score(product),
                float(product.business_score or 0),
                -original_index[id(product)],
            ),
            reverse=True,
        )

        keep_limit = max_per_use_case
        exceptional_count = sum(1 for product in group if _is_exceptional(product))
        if exceptional_count > max_per_use_case:
            # 极高价值项目可以突破数量上限，但“高度重复”永远不能靠高分绕过语义去重。
            keep_limit = max_per_use_case + 1

        kept = [primary]
        for product in ranked_others:
            if any(_same_semantic_opportunity(product, existing) for existing in kept):
                semantic_suppressed += 1
                continue
            if len(kept) >= keep_limit:
                continue
            kept.append(product)

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
        "semantic_suppressed": semantic_suppressed,
        "use_case_suppressed": use_case_suppressed,
        "lane_suppressed": lane_suppressed,
        "use_cases": dict(use_case_counts),
        "lanes": dict(lane_counts),
    }

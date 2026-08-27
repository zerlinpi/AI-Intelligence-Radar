import re
from typing import Dict

from app.scoring import business_opportunity_profile


# GitHub 可以额外保留真正可复用的开发基础设施/工程突破，
# 但仅有“AI/Agent/Chat”字样的普通 Demo 不视为可产品化开发能力。
GITHUB_DEVELOPER_PRODUCT_SIGNALS = (
    "sdk",
    "api",
    "framework",
    "library",
    "runtime",
    "compiler",
    "engine",
    "toolkit",
    "cli",
    "server",
    "platform",
    "database",
    "workflow",
    "automation",
    "firmware",
    "embedded",
    "edge ai",
    "on-device",
    "mcu",
    "esp32",
    "robotics",
    "computer vision",
)

# 跨境关键词必须落到真实工具/代码形态，避免 “Amazon reviews dataset”
# 仅靠 Amazon/reviews 之类词进入日报。
GITHUB_CROSS_BORDER_PRODUCT_SIGNALS = (
    "sdk",
    "api",
    "tool",
    "app",
    "platform",
    "workflow",
    "automation",
    "dashboard",
    "plugin",
    "extension",
    "integration",
    "analytics",
    "copilot",
    "assistant",
    "agent",
    "scraper",
    "crawler",
    "monitor",
    "optimizer",
    "generator",
)

# 这些词经常让教程、模板、演示仓库因为同时出现 framework/runtime 等词被误判为工程突破。
# 只用于“纯开发基础设施”路径；若项目本身有明确实体商品价值，不会被这里误杀。
GITHUB_LOW_VALUE_SIGNALS = (
    "demo",
    "example project",
    "example app",
    "tutorial",
    "course",
    "workshop tutorial",
    "boilerplate",
    "starter template",
    "template repo",
    "toy project",
    "awesome list",
    "prompt collection",
)

# 对论文和模型而言，这些词通常代表“研究材料”而非可直接开发的机会。
# 它们不是绝对否决项；如果同时存在明确跨境工作流或实体商品验证路径，仍可通过。
RESEARCH_ONLY_SIGNALS = (
    "benchmark",
    "benchmarking",
    "dataset",
    "survey",
    "leaderboard",
    "ablation",
    "synthetic benchmark",
    "evaluation suite",
    "research benchmark",
    "taxonomy",
    "literature review",
)

# 论文/模型若声称可落到硬件或商品，至少应出现某种实际验证/部署语义，
# 防止“camera + sensor + smart device”只在背景描述里共现就被判定可售产品。
APPLIED_VALIDATION_SIGNALS = (
    "prototype",
    "prototype system",
    "deployed",
    "deployment",
    "deployable",
    "demonstrate",
    "demonstrates",
    "real-time",
    "real time",
    "latency",
    "memory footprint",
    "power consumption",
    "energy consumption",
    "on-device inference",
    "embedded hardware",
    "field test",
    "user study",
    "production",
)

# 直接跨境业务用途必须比 “amazon/reviews” 这种宽泛词更具体。
DIRECT_CROSS_BORDER_APPLICATION_SIGNALS = (
    "product listing",
    "listing optimization",
    "keyword research",
    "product research",
    "competitor research",
    "inventory",
    "fulfillment",
    "logistics",
    "pricing",
    "price tracking",
    "advertising",
    "ad creative",
    "customer service",
    "customer support",
    "localization",
    "sourcing",
    "procurement",
    "seller workflow",
    "merchant workflow",
)

DIMENSION_THRESHOLDS = {
    "cross_border": 12,
    "technical_frontier": 10,
    "hardware_enablement": 10,
    "physical_product": 8,
}

# 不同来源的信息结构不同，不能用同一个“描述长度”标准。
# 分数是证据充分度，不是热度；只负责决定是否值得进入后续排序/DeepSeek。
SOURCE_EVIDENCE_MIN = {
    "github": 25,
    "arxiv": 45,
    "huggingface": 50,
    "producthunt": 30,
    "hackernews": 30,
}
DEFAULT_EVIDENCE_MIN = 25

# 论文和 Model Card 经常用“without hardware deployment / no sensor integration”描述研究边界。
# 这些否定句里的关键词不能反过来成为“硬件开发/实体商品”的正面证据。
_NEGATED_CLAUSE_PATTERNS = (
    re.compile(
        r"\bwithout\b.*?(?=\b(?:but|however|yet|while|although)\b|[.;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:does\s+not|doesn't|do\s+not|don't)\s+"
        r"(?:describe|support|target|include|provide|address|offer|cover|evaluate|demonstrate)\b"
        r".*?(?=\b(?:but|however|yet|while|although)\b|[.;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:not\s+intended|not\s+designed|not\s+targeted|not\s+validated)\s+for\b"
        r".*?(?=\b(?:but|however|yet|while|although)\b|[.;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:no|lacks?|lack\s+of|no\s+evidence\s+of|no\s+support\s+for)\s+"
        r"(?:clear\s+|direct\s+|demonstrated\s+|practical\s+)?"
        r"(?:cross[- ]border|e-?commerce|amazon|shopify|hardware|embedded|sensor|physical|"
        r"consumer\s+(?:device|hardware|product)|productization|commercial\s+product)\b"
        r".*?(?=\b(?:but|however|yet|while|although)\b|[.;!?]|$)",
        re.IGNORECASE,
    ),
)


def _text(item: Dict) -> str:
    metrics = item.get("metrics") or {}
    extra = []
    if isinstance(metrics, dict):
        for key in ("tags", "topics", "pipeline_tag", "library_name", "language"):
            value = metrics.get(key)
            if isinstance(value, list):
                extra.extend(str(part) for part in value)
            elif value:
                extra.append(str(value))
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            *extra,
        ]
    ).lower()


def _contains(text: str, keyword: str) -> bool:
    keyword = keyword.lower().strip()
    if re.fullmatch(r"[a-z0-9]+", keyword):
        return bool(re.search(rf"\b{re.escape(keyword)}(?:s|es)?\b", text))
    return keyword in text


def _contains_any(item: Dict, signals) -> bool:
    text = _text(item)
    return any(_contains(text, keyword) for keyword in signals)


def _dimension(profile: Dict, name: str) -> float:
    try:
        return float((profile.get("dimensions") or {}).get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _has_github_developer_product_signal(item: Dict) -> bool:
    return _contains_any(item, GITHUB_DEVELOPER_PRODUCT_SIGNALS)


def _has_github_cross_border_product_signal(item: Dict) -> bool:
    return _contains_any(item, GITHUB_CROSS_BORDER_PRODUCT_SIGNALS)


def _has_github_low_value_signal(item: Dict) -> bool:
    return _contains_any(item, GITHUB_LOW_VALUE_SIGNALS)


def _has_research_only_signal(item: Dict) -> bool:
    return _contains_any(item, RESEARCH_ONLY_SIGNALS)


def _has_applied_validation_signal(item: Dict) -> bool:
    return _contains_any(item, APPLIED_VALIDATION_SIGNALS)


def _has_direct_cross_border_application(item: Dict) -> bool:
    return _contains_any(item, DIRECT_CROSS_BORDER_APPLICATION_SIGNALS)


def _evidence_quality(item: Dict) -> int:
    """返回 0-100 的来源证据质量分，不把热度当作证据。"""
    source = str(item.get("source") or "").lower()
    description = " ".join(str(item.get("description") or "").split())
    metrics = item.get("metrics") or {}
    metrics = metrics if isinstance(metrics, dict) else {}
    score = 0

    if source == "github":
        if len(description) >= 120:
            score += 35
        elif len(description) >= 60:
            score += 30
        elif len(description) >= 18:
            score += 25

        topics = metrics.get("topics") or []
        if isinstance(topics, list):
            score += min(len(topics) * 4, 12)
        if metrics.get("readme_evidence"):
            chars = int(metrics.get("readme_chars") or 0)
            score += 30 if chars >= 300 else 20
        if str(metrics.get("language") or "").strip():
            score += 8
        if str(metrics.get("license_spdx") or "").strip():
            score += 7
        if str(metrics.get("homepage") or "").strip():
            score += 4

    elif source == "arxiv":
        if len(description) >= 500:
            score += 65
        elif len(description) >= 250:
            score += 58
        elif len(description) >= 100:
            score += 45
        topics = metrics.get("topics") or []
        if isinstance(topics, list) and topics:
            score += min(len(topics) * 3, 10)
        if _has_applied_validation_signal(item):
            score += 12

    elif source == "huggingface":
        if str(metrics.get("pipeline_tag") or "").strip():
            score += 22
        if str(metrics.get("library_name") or "").strip():
            score += 18
        tags = metrics.get("tags") or []
        if isinstance(tags, list):
            score += min(len(tags) * 5, 20)
        if metrics.get("model_card_evidence"):
            chars = int(metrics.get("model_card_chars") or 0)
            score += 30 if chars >= 300 else 20
        elif len(description) >= 120:
            score += 20
        elif len(description) >= 55:
            score += 12

    elif source in {"producthunt", "hackernews"}:
        if len(description) >= 100:
            score += 55
        elif len(description) >= 55:
            score += 45
        elif len(description) >= 35:
            score += 30
        if str(item.get("url") or "").strip():
            score += 10
        metrics_values = (
            metrics.get("upvotes"),
            metrics.get("comments"),
            item.get("upvotes"),
            item.get("comments"),
        )
        if any(value not in (None, "", 0, 0.0) for value in metrics_values):
            score += 10

    else:
        if len(description) >= 80:
            score += 50
        elif len(description) >= 24:
            score += 30

    return min(int(score), 100)


def _evidence_sufficient(item: Dict) -> bool:
    source = str(item.get("source") or "").lower()
    return _evidence_quality(item) >= SOURCE_EVIDENCE_MIN.get(source, DEFAULT_EVIDENCE_MIN)


def _strip_negated_application_claims(value: str) -> str:
    """删除明确否定的应用范围子句，避免关键词评分把“没有硬件用途”当成硬件证据。

    只删除否定子句本身；遇到 but/however/yet/while/although 会停止，保留后面的正面转折。
    该函数只用于相关性评分，不修改最终展示或保存的原始文本。
    """
    text = " ".join(str(value or "").split())
    for pattern in _NEGATED_CLAUSE_PATTERNS:
        text = pattern.sub(" ", text)
    return " ".join(text.split())


def _profile_for_eligibility(item: Dict, source: str) -> Dict:
    """论文/模型先屏蔽否定应用声明，再计算真正可用于资格判断的机会画像。"""
    if source not in {"arxiv", "huggingface"}:
        return business_opportunity_profile(item)

    cleaned = dict(item)
    cleaned["description"] = _strip_negated_application_claims(item.get("description") or "")

    metrics = item.get("metrics") or {}
    if isinstance(metrics, dict):
        cleaned["metrics"] = dict(metrics)

    return business_opportunity_profile(cleaned)


def _physical_product_path(profile: Dict) -> bool:
    """实体商品路径必须同时有硬件能力、实体商品语义和可识别商品品类。"""
    hardware = _dimension(profile, "hardware_enablement") >= DIMENSION_THRESHOLDS["hardware_enablement"]
    physical = _dimension(profile, "physical_product") >= DIMENSION_THRESHOLDS["physical_product"]
    categories = list(profile.get("product_categories") or [])
    return bool(hardware and physical and categories)


def _primary_use_case(item: Dict, profile: Dict, source: str, physical_product_path: bool) -> str:
    text = _text(item)

    cross_border_cases = (
        ("Listing/内容", ("product listing", "listing optimization", "localization", "translation", "seo")),
        ("选品/竞品", ("product research", "competitor research", "sourcing", "procurement")),
        ("广告/增长", ("advertising", "ad creative", "meta ads", "google ads", "affiliate", "influencer", "ugc")),
        ("库存/履约", ("inventory", "fulfillment", "warehouse", "shipping", "logistics", "returns")),
        ("客服/评论", ("customer support", "customer service", "review analysis", "reviews")),
        ("定价", ("pricing", "price tracking")),
    )
    for label, signals in cross_border_cases:
        if any(_contains(text, signal) for signal in signals):
            return label

    categories = list(profile.get("product_categories") or [])
    if physical_product_path and categories:
        return f"实体商品·{categories[0]}"

    if source == "github":
        developer_cases = (
            ("开发基础设施·端侧/推理", ("runtime", "compiler", "quantization", "on-device", "edge ai")),
            ("开发基础设施·视觉/机器人", ("computer vision", "robotics", "slam", "robot")),
            ("开发基础设施·Agent", ("agent memory", "multi-agent", "tool use", "agentic")),
            ("开发基础设施·SDK/API", ("sdk", "api", "framework", "library", "toolkit")),
        )
        for label, signals in developer_cases:
            if any(_contains(text, signal) for signal in signals):
                return label

    return "其他"


def _primary_lane(source: str, cross_border: bool, physical_product_path: bool, developer_product: bool) -> str:
    if cross_border:
        return "跨境业务工具"
    if physical_product_path:
        return "实体商品/硬件"
    if source == "github" and developer_product:
        return "开发基础设施"
    return "其他"


def report_eligibility(item: Dict) -> Dict:
    """判断一个项目是否有资格进入最终日报。

    热度和新鲜度只能影响已合格项目之间的排序，不能让无业务价值、证据不足、
    或只有宽泛关键词的项目绕过本门槛。
    """
    item = item if isinstance(item, dict) else {}
    source = str(item.get("source") or "").lower()
    profile = _profile_for_eligibility(item, source)

    cross_border = _dimension(profile, "cross_border") >= DIMENSION_THRESHOLDS["cross_border"]
    technical = _dimension(profile, "technical_frontier") >= DIMENSION_THRESHOLDS["technical_frontier"]
    hardware = _dimension(profile, "hardware_enablement") >= DIMENSION_THRESHOLDS["hardware_enablement"]
    physical = _dimension(profile, "physical_product") >= DIMENSION_THRESHOLDS["physical_product"]
    product_categories = list(profile.get("product_categories") or [])
    physical_product_path = _physical_product_path(profile)
    evidence_quality = _evidence_quality(item)
    evidence_sufficient = _evidence_sufficient(item)
    research_only = _has_research_only_signal(item)
    applied_validation = _has_applied_validation_signal(item)
    direct_cross_border_application = _has_direct_cross_border_application(item)

    eligible = False
    reason = "与跨境业务、硬件开发或实体商品机会无直接关系"
    developer_product = False

    if source == "github":
        low_value_example = _has_github_low_value_signal(item)
        developer_product = (
            technical
            and _has_github_developer_product_signal(item)
            and not low_value_example
        )
        cross_border_product = cross_border and _has_github_cross_border_product_signal(item)

        eligible = cross_border_product or physical_product_path or developer_product
        if eligible:
            if cross_border_product:
                reason = "具备明确跨境业务用途和可执行代码/工具形态"
            elif physical_product_path:
                reason = "具备明确硬件能力、实体商品形态和商品品类"
            else:
                reason = "具备可复用的开发基础设施或工程突破"
        elif cross_border:
            reason = "出现跨境关键词，但缺少可直接使用的工具、自动化或代码形态"
        elif low_value_example and technical:
            reason = "主要是教程、模板或演示仓库，缺少可复用产品/工程价值证据"
        elif hardware or physical:
            reason = "存在硬件或商品关键词，但尚未形成可信的实体商品落地链路"

    elif source in {"arxiv", "huggingface"}:
        cross_border_applied = cross_border and direct_cross_border_application
        physical_applied = physical_product_path and (applied_validation or source == "huggingface")
        eligible = cross_border_applied or physical_applied

        if eligible:
            if cross_border_applied:
                reason = "具有明确跨境业务工作流或运营用途"
            else:
                reason = "具备可验证的硬件到实体商品落地路径"
        elif cross_border and not direct_cross_border_application:
            reason = "提到跨境平台/数据，但缺少可直接用于运营或开发的具体工作流"
        elif research_only and not applied_validation:
            reason = "主要是benchmark、dataset、survey等研究材料，缺少实际应用验证"
        elif hardware or physical or technical:
            reason = "具有技术或硬件研究价值，但缺少跨境用途或明确实体商品落地路径"

    elif source in {"producthunt", "hackernews"}:
        cross_border_applied = cross_border and direct_cross_border_application
        eligible = cross_border_applied or physical_product_path
        if eligible:
            reason = (
                "具备明确跨境业务用途"
                if cross_border_applied
                else "具备明确硬件与实体商品机会"
            )
        elif cross_border:
            reason = "与电商相关但用途过于宽泛，缺少具体运营/产品价值路径"
        elif hardware or physical:
            reason = "存在硬件/商品概念，但缺少足够证据证明能形成实体产品"

    else:
        eligible = (cross_border and direct_cross_border_application) or physical_product_path
        if eligible:
            reason = "满足跨境或实体产品价值门槛"

    if eligible and not evidence_sufficient:
        eligible = False
        reason = f"公开信息不足，证据质量={evidence_quality}，无法可靠判断实际用途或产品化路径"

    primary_lane = _primary_lane(source, cross_border, physical_product_path, developer_product)
    primary_use_case = _primary_use_case(item, profile, source, physical_product_path)

    strongest_dimension = max(
        (
            ("cross_border", _dimension(profile, "cross_border")),
            ("technical_frontier", _dimension(profile, "technical_frontier")),
            ("hardware_enablement", _dimension(profile, "hardware_enablement")),
            ("physical_product", _dimension(profile, "physical_product")),
        ),
        key=lambda row: row[1],
    )[1]
    confidence = min(
        100,
        round(evidence_quality * 0.65 + min(strongest_dimension / 30 * 100, 100) * 0.35),
    )

    return {
        "eligible": bool(eligible),
        "reason": reason,
        "profile": profile,
        "cross_border": cross_border,
        "technical_frontier": technical,
        "hardware_enablement": hardware,
        "physical_product": physical,
        "physical_product_path": physical_product_path,
        "product_categories": product_categories,
        "evidence_sufficient": evidence_sufficient,
        "evidence_quality": evidence_quality,
        "research_only": research_only,
        "applied_validation": applied_validation,
        "primary_lane": primary_lane,
        "primary_use_case": primary_use_case,
        "eligibility_confidence": confidence,
    }


def attach_eligibility_metrics(item: Dict, result: Dict) -> Dict:
    """把资格判断写回 metrics，方便日志、DeepSeek 和数据库追踪。"""
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics

    history_update_reason = str(metrics.get("history_material_update_reason") or "").strip()

    profile = result.get("profile") or {}
    evidence = list(profile.get("evidence") or [])
    if history_update_reason:
        evidence = [f"重大更新:{history_update_reason}"] + [
            value for value in evidence if value != history_update_reason
        ]

    metrics["report_eligible"] = bool(result.get("eligible"))
    metrics["evidence_sufficient"] = bool(result.get("evidence_sufficient"))
    metrics["evidence_quality"] = int(result.get("evidence_quality") or 0)
    metrics["eligibility_confidence"] = int(result.get("eligibility_confidence") or 0)
    metrics["physical_product_path"] = bool(result.get("physical_product_path"))
    metrics["research_only"] = bool(result.get("research_only"))
    metrics["applied_validation"] = bool(result.get("applied_validation"))
    metrics["primary_lane"] = str(result.get("primary_lane") or "其他")
    metrics["primary_use_case"] = str(result.get("primary_use_case") or "其他")
    metrics["eligibility_reason"] = str(result.get("reason") or "")
    metrics["opportunity_score"] = profile.get("opportunity_score", 0)
    metrics["opportunity_dimensions"] = dict(profile.get("dimensions") or {})
    metrics["opportunity_evidence"] = evidence
    metrics["product_categories"] = list(profile.get("product_categories") or [])
    metrics["priority_tags"] = list(profile.get("tags") or [])
    return item

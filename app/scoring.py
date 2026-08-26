from datetime import datetime, timezone
import re


# 业务相关性不再只判断“是不是电商工具”，而是同时评估：
# 1) 跨境电商直接价值；2) 技术前沿/工程创新；3) 硬件开发赋能；4) 可形成美国市场实体商品的机会。
CROSS_BORDER_SIGNALS = (
    ("amazon", 12),
    ("shopify", 10),
    ("tiktok shop", 10),
    ("walmart", 8),
    ("etsy", 7),
    ("seller", 7),
    ("merchant", 6),
    ("ecommerce", 7),
    ("e-commerce", 7),
    ("cross-border", 8),
    ("cross border", 8),
    ("product listing", 8),
    ("listing optimization", 9),
    ("listing", 5),
    ("product research", 7),
    ("competitor research", 6),
    ("keyword research", 5),
    ("fulfillment", 6),
    ("inventory", 5),
    ("warehouse", 4),
    ("shipping", 4),
    ("logistics", 5),
    ("returns", 4),
    ("customer support", 4),
    ("customer service", 4),
    ("localization", 5),
    ("translation", 3),
    ("pricing", 4),
    ("price tracking", 5),
    ("advertising", 4),
    ("ad creative", 5),
    ("meta ads", 5),
    ("google ads", 5),
    ("seo", 4),
    ("affiliate", 4),
    ("influencer", 4),
    ("ugc", 4),
    ("review analysis", 5),
    ("reviews", 3),
    ("sourcing", 5),
    ("procurement", 5),
)

TECHNICAL_FRONTIER_SIGNALS = (
    ("agent memory", 8),
    ("long-term memory", 7),
    ("long horizon", 7),
    ("long-horizon", 7),
    ("reasoning", 4),
    ("test-time", 5),
    ("world model", 7),
    ("computer use", 7),
    ("tool use", 5),
    ("multi-agent", 5),
    ("agentic", 5),
    ("rag", 4),
    ("retrieval", 3),
    ("multimodal", 5),
    ("vision-language", 6),
    ("vision language", 6),
    ("speech-to-speech", 6),
    ("real-time voice", 5),
    ("inference engine", 6),
    ("inference runtime", 6),
    ("runtime", 3),
    ("compiler", 5),
    ("quantization", 5),
    ("distillation", 4),
    ("on-device", 6),
    ("edge ai", 6),
    ("3d reconstruction", 6),
    ("slam", 6),
    ("embodied ai", 7),
    ("robot learning", 6),
    ("foundation model", 4),
    ("new architecture", 6),
    ("novel architecture", 7),
    ("framework", 3),
    ("sdk", 3),
)

HARDWARE_ENABLEMENT_SIGNALS = (
    ("embedded", 6),
    ("embedded ai", 8),
    ("microcontroller", 7),
    ("mcu", 6),
    ("esp32", 8),
    ("arduino", 6),
    ("raspberry pi", 6),
    ("firmware", 7),
    ("rtos", 7),
    ("bluetooth", 5),
    ("ble", 6),
    ("iot", 5),
    ("edge ai", 8),
    ("on-device", 7),
    ("sensor", 5),
    ("camera", 4),
    ("computer vision", 6),
    ("vision-language", 5),
    ("robotics", 7),
    ("robot", 5),
    ("motor control", 7),
    ("motion control", 6),
    ("lidar", 7),
    ("imu", 7),
    ("mqtt", 5),
    ("can bus", 6),
    ("serial", 3),
    ("wearable", 6),
    ("smart home", 5),
    ("speech recognition", 4),
    ("keyword spotting", 6),
    ("object detection", 5),
    ("pose estimation", 5),
)

PHYSICAL_PRODUCT_SIGNALS = (
    ("consumer device", 8),
    ("hardware product", 9),
    ("smart device", 7),
    ("wearable", 8),
    ("smart home", 7),
    ("home appliance", 7),
    ("kitchen", 5),
    ("pet", 5),
    ("fitness", 5),
    ("sports", 4),
    ("outdoor", 4),
    ("automotive", 6),
    ("vehicle", 4),
    ("mobility", 5),
    ("wheelchair", 7),
    ("baby", 5),
    ("toy", 5),
    ("tool", 3),
    ("security camera", 7),
    ("camera", 4),
    ("lighting", 4),
    ("cleaning", 4),
    ("personal care", 5),
    ("health device", 7),
    ("sleep", 4),
    ("cycling", 4),
    ("sensor", 4),
    ("robot", 5),
    ("portable", 3),
    ("battery", 4),
)

# 实体商品候选进一步映射到用户真正能研发/销售的品类。品类必须建立在
# “硬件开发”或“实体商品机会”已经有足够信号的前提上，避免把 software tool 误判成工具五金。
PRODUCT_CATEGORY_SIGNALS = {
    "消费电子": (
        ("consumer device", 9),
        ("smart device", 8),
        ("camera", 5),
        ("wearable", 6),
        ("headphone", 6),
        ("earbud", 6),
        ("speaker", 5),
        ("display", 4),
        ("bluetooth", 3),
        ("battery", 3),
        ("charging", 4),
    ),
    "智能家居": (
        ("smart home", 10),
        ("home appliance", 9),
        ("lighting", 6),
        ("cleaning", 6),
        ("kitchen", 5),
        ("thermostat", 7),
        ("home automation", 8),
    ),
    "宠物用品": (
        ("pet camera", 10),
        ("pet", 8),
        ("dog", 6),
        ("cat", 6),
        ("feeder", 8),
        ("litter", 8),
        ("leash", 6),
    ),
    "汽车出行": (
        ("automotive", 10),
        ("vehicle", 7),
        ("dashcam", 10),
        ("car", 5),
        ("can bus", 8),
        ("cycling", 5),
        ("e-bike", 8),
        ("ebike", 8),
    ),
    "运动户外": (
        ("fitness", 8),
        ("sports", 6),
        ("outdoor", 6),
        ("cycling", 7),
        ("treadmill", 9),
        ("gym", 6),
        ("wearable", 4),
    ),
    "工具DIY": (
        ("power tool", 10),
        ("tool", 4),
        ("workshop", 7),
        ("measurement", 6),
        ("inspection", 6),
        ("laser", 5),
    ),
    "健康辅助": (
        ("health device", 10),
        ("wheelchair", 10),
        ("mobility aid", 10),
        ("rehabilitation", 9),
        ("rehab", 8),
        ("sleep", 6),
        ("posture", 6),
        ("mobility", 6),
    ),
    "安防": (
        ("security camera", 10),
        ("surveillance", 9),
        ("doorbell", 8),
        ("intrusion", 8),
        ("access control", 8),
    ),
    "办公桌面": (
        ("desk", 8),
        ("office", 7),
        ("ergonomic", 8),
        ("keyboard", 7),
        ("mouse", 6),
        ("desktop device", 8),
    ),
}

PRODUCTIZABLE_KEYWORDS = (
    "saas",
    "platform",
    "tool",
    "app",
    "api",
    "sdk",
    "agent",
    "copilot",
    "assistant",
    "automation",
    "workflow",
    "dashboard",
    "browser",
    "extension",
    "plugin",
    "integration",
    "analytics",
    "generator",
    "monitor",
    "search",
    "scraper",
    "service",
    "device",
    "hardware",
    "firmware",
)

DIMENSION_THRESHOLDS = {
    "cross_border": 12,
    "technical_frontier": 10,
    "hardware_enablement": 10,
    "physical_product": 8,
}

DIMENSION_TAGS = {
    "cross_border": "跨境电商",
    "technical_frontier": "技术前沿",
    "hardware_enablement": "硬件开发",
    "physical_product": "实体商品机会",
}


def _normalize(value, divisor, weight):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0
    if value < 0:
        value = 0
    return min(value / divisor * weight, weight)


def _metric(item, key):
    if not isinstance(item, dict):
        return 0
    if key in item:
        return item.get(key) or 0
    metrics = item.get("metrics") or {}
    if isinstance(metrics, dict):
        return metrics.get(key) or 0
    return 0


def _search_text(item) -> str:
    if not isinstance(item, dict):
        return ""
    metrics = item.get("metrics") or {}
    metric_text = ""
    if isinstance(metrics, dict):
        for key in ("tags", "pipeline_tag", "library_name", "topics"):
            value = metrics.get(key)
            if isinstance(value, list):
                metric_text += " " + " ".join(str(part) for part in value)
            elif value:
                metric_text += " " + str(value)
    parts = [
        item.get("title"),
        item.get("description"),
        item.get("category"),
        item.get("source"),
        metric_text,
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    keyword = keyword.lower().strip()
    if re.fullmatch(r"[a-z0-9]+", keyword):
        pattern = rf"\b{re.escape(keyword)}(?:s|es)?\b"
        return bool(re.search(pattern, text))
    return keyword in text


def _signal_score(text: str, signals, cap: int):
    score = 0
    hits = []
    for keyword, weight in signals:
        if _contains_keyword(text, keyword):
            score += weight
            hits.append(keyword)
    return min(score, cap), hits


def _product_categories(text: str, dimensions: dict):
    """在硬件/实体机会成立后，把候选映射为最多三个可销售商品品类。"""
    if (
        dimensions.get("physical_product", 0) < DIMENSION_THRESHOLDS["physical_product"]
        and dimensions.get("hardware_enablement", 0) < DIMENSION_THRESHOLDS["hardware_enablement"]
    ):
        return [], {}

    scored = []
    category_scores = {}
    for category, signals in PRODUCT_CATEGORY_SIGNALS.items():
        score, _ = _signal_score(text, signals, 20)
        category_scores[category] = score
        if score >= 6:
            scored.append((score, category))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    categories = [category for _, category in scored[:3]]
    return categories, category_scores


def _opportunity_evidence(dimensions: dict, hits: dict):
    """提取最有解释力的本地命中词，供飞书和 DeepSeek 看到筛选依据。"""
    ranked = sorted(dimensions.items(), key=lambda row: row[1], reverse=True)
    evidence = []
    seen = set()
    for key, score in ranked:
        if score < DIMENSION_THRESHOLDS.get(key, 999):
            continue
        for hit in hits.get(key, []):
            if hit in seen:
                continue
            seen.add(hit)
            evidence.append(hit)
            if len(evidence) >= 4:
                return evidence
    return evidence


def business_opportunity_profile(item):
    """返回项目四维机会画像、商品品类和可解释证据。

    这是本地、可解释的第一阶段筛选，不声称仅凭关键词即可证明某技术“全球首创”。
    “技术前沿”表示值得进一步由 DeepSeek 判断新颖性与工程价值的候选信号。
    """
    text = _search_text(item)
    source = str(item.get("source") or "").lower() if isinstance(item, dict) else ""

    cross_border, cross_hits = _signal_score(text, CROSS_BORDER_SIGNALS, 30)
    technical, technical_hits = _signal_score(text, TECHNICAL_FRONTIER_SIGNALS, 25)
    hardware, hardware_hits = _signal_score(text, HARDWARE_ENABLEMENT_SIGNALS, 25)
    physical, physical_hits = _signal_score(text, PHYSICAL_PRODUCT_SIGNALS, 20)

    # arXiv/Hugging Face/GitHub 只在已经出现技术信号时给予少量来源可信度加成，
    # 避免把“任何论文/任何仓库”都误判为技术前沿。
    if technical > 0 and source in {"arxiv", "huggingface", "github"}:
        technical = min(technical + 3, 25)

    # 实体商品机会通常需要技术/硬件落地条件。硬件信号较强时给予少量联动加分，
    # 但不会仅凭“AI”二字判定为 Amazon 可售商品。
    if physical > 0 and hardware >= 8:
        physical = min(physical + 4, 20)

    dimensions = {
        "cross_border": cross_border,
        "technical_frontier": technical,
        "hardware_enablement": hardware,
        "physical_product": physical,
    }
    hits = {
        "cross_border": cross_hits,
        "technical_frontier": technical_hits,
        "hardware_enablement": hardware_hits,
        "physical_product": physical_hits,
    }

    product_categories, category_scores = _product_categories(text, dimensions)
    evidence = _opportunity_evidence(dimensions, hits)

    # 强单维机会也应获得较高优先级，因此总机会分 = 四维合计 + 最强维度奖励。
    # 已经映射到真实商品品类的候选再得到少量加分，使“可做成什么”优先于泛硬件概念。
    strongest = max(dimensions.values()) if dimensions else 0
    category_bonus = min(len(product_categories) * 5, 10)
    opportunity_score = min(sum(dimensions.values()) + strongest + category_bonus, 100)

    tags = [
        DIMENSION_TAGS[key]
        for key, score in dimensions.items()
        if score >= DIMENSION_THRESHOLDS[key]
    ]
    tags.extend(f"商品·{category}" for category in product_categories[:2])
    if evidence:
        tags.append("证据·" + "/".join(evidence[:3]))

    product_signal = any(
        _contains_keyword(text, keyword)
        for keyword in PRODUCTIZABLE_KEYWORDS
    )
    if source == "producthunt" or product_signal or tags:
        tags.append("可产品化")

    # 去重且保持稳定顺序。
    tags = list(dict.fromkeys(tags))

    return {
        "opportunity_score": round(float(opportunity_score), 2),
        "dimensions": dimensions,
        "tags": tags,
        "hits": hits,
        "evidence": evidence,
        "product_categories": product_categories,
        "product_category_scores": category_scores,
    }


def _apply_profile_metrics(item, profile):
    """把可解释画像写回 metrics；RadarItem.to_dict 的 metrics 与对象共享，可直接进入后续 AI 分析。"""
    if not isinstance(item, dict):
        return
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics
    metrics["opportunity_score"] = profile["opportunity_score"]
    metrics["opportunity_dimensions"] = dict(profile["dimensions"])
    metrics["opportunity_evidence"] = list(profile["evidence"])
    metrics["product_categories"] = list(profile["product_categories"])


def priority_tags(item):
    profile = business_opportunity_profile(item)
    _apply_profile_metrics(item, profile)
    return list(profile["tags"])


def calculate_priority_score(item):
    """返回 0-100 的业务/技术机会分，不改变早期热度分本身。"""
    profile = business_opportunity_profile(item)
    _apply_profile_metrics(item, profile)
    return profile["opportunity_score"]


def age_hours(item):
    created_at = item.get("created_at") if isinstance(item, dict) else None
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - created).total_seconds() / 3600, 0)
    except Exception:
        return None


def freshness_score(item):
    hours = age_hours(item)
    if hours is None:
        return 0
    if hours <= 6:
        return 40
    if hours <= 24:
        return 36
    if hours <= 72:
        return 30
    if hours <= 168:
        return 22
    if hours <= 336:
        return 10
    return 0


def calculate_score(item):
    """计算 0-100 的早期趋势分：新鲜度、增长速度、早期互动、来源动量。"""
    if not isinstance(item, dict):
        return 0

    hours = age_hours(item)
    age_days = max((hours or 24) / 24, 0.25)

    stars_per_day = float(_metric(item, "stars") or 0) / age_days
    upvotes_per_day = float(_metric(item, "upvotes") or 0) / age_days
    downloads_per_day = float(_metric(item, "downloads") or 0) / age_days
    forks_per_day = float(_metric(item, "forks") or 0) / age_days
    comments_per_day = float(_metric(item, "comments") or 0) / age_days
    likes_per_day = float(_metric(item, "likes") or 0) / age_days

    community_velocity = (
        _normalize(stars_per_day, 150, 20)
        + _normalize(upvotes_per_day, 80, 10)
        + _normalize(downloads_per_day, 10000, 5)
    )
    engagement = (
        _normalize(forks_per_day, 30, 5)
        + _normalize(comments_per_day, 25, 5)
        + _normalize(likes_per_day, 30, 5)
    )
    source_momentum = _normalize(_metric(item, "momentum"), 5000, 10)

    score = freshness_score(item) + community_velocity + engagement + source_momentum
    return round(min(max(score, 0), 100), 2)

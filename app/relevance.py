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


DIMENSION_THRESHOLDS = {
    "cross_border": 12,
    "technical_frontier": 10,
    "hardware_enablement": 10,
    "physical_product": 8,
}


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


def _dimension(profile: Dict, name: str) -> float:
    try:
        return float((profile.get("dimensions") or {}).get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _has_github_developer_product_signal(item: Dict) -> bool:
    text = _text(item)
    return any(_contains(text, keyword) for keyword in GITHUB_DEVELOPER_PRODUCT_SIGNALS)


def _evidence_sufficient(item: Dict) -> bool:
    """防止只有标题命中关键词、却没有足够公开材料支撑后续判断。"""
    source = str(item.get("source") or "").lower()
    description = " ".join(str(item.get("description") or "").split())
    metrics = item.get("metrics") or {}
    metrics = metrics if isinstance(metrics, dict) else {}

    if source == "github":
        topics = metrics.get("topics") or []
        topic_count = len(topics) if isinstance(topics, list) else 0
        return len(description) >= 18 or topic_count >= 2

    if source == "arxiv":
        # arXiv 合格候选应至少具有能够解释研究方法/应用路径的摘要，而不是只有论文标题。
        return len(description) >= 100

    if source == "huggingface":
        pipeline_tag = str(metrics.get("pipeline_tag") or "").strip()
        library_name = str(metrics.get("library_name") or "").strip()
        tags = metrics.get("tags") or []
        tag_count = len(tags) if isinstance(tags, list) else 0
        return bool(pipeline_tag and (library_name or tag_count >= 2)) or len(description) >= 55

    if source in {"producthunt", "hackernews"}:
        return len(description) >= 35

    return len(description) >= 24


def report_eligibility(item: Dict) -> Dict:
    """判断一个项目是否有资格进入最终日报。

    热度和新鲜度只能影响已合格项目之间的排序，不能让无业务价值或证据不足的项目绕过本门槛。
    """
    item = item if isinstance(item, dict) else {}
    source = str(item.get("source") or "").lower()
    profile = business_opportunity_profile(item)

    cross_border = _dimension(profile, "cross_border") >= DIMENSION_THRESHOLDS["cross_border"]
    technical = _dimension(profile, "technical_frontier") >= DIMENSION_THRESHOLDS["technical_frontier"]
    hardware = _dimension(profile, "hardware_enablement") >= DIMENSION_THRESHOLDS["hardware_enablement"]
    physical = _dimension(profile, "physical_product") >= DIMENSION_THRESHOLDS["physical_product"]
    product_categories = list(profile.get("product_categories") or [])
    evidence_sufficient = _evidence_sufficient(item)

    eligible = False
    reason = "与跨境业务、硬件开发或实体商品机会无直接关系"

    if source == "github":
        developer_product = technical and _has_github_developer_product_signal(item)
        eligible = cross_border or hardware or physical or developer_product
        if eligible:
            if cross_border:
                reason = "可直接用于跨境电商业务"
            elif hardware or physical:
                reason = "可用于硬件/实体商品开发"
            else:
                reason = "具备可复用的开发基础设施或工程突破"
    elif source in {"arxiv", "huggingface"}:
        # 论文和模型门槛更严格：纯技术前沿但无法服务跨境业务、硬件或实体商品时不推送。
        eligible = cross_border or hardware or physical
        if eligible:
            reason = (
                "可直接用于跨境业务"
                if cross_border
                else "可进入硬件或实体商品开发链路"
            )
    elif source in {"producthunt", "hackernews"}:
        eligible = cross_border or hardware or physical
        if eligible:
            reason = (
                "可直接用于跨境业务"
                if cross_border
                else "具备硬件/实体商品机会"
            )
    else:
        eligible = cross_border or hardware or physical
        if eligible:
            reason = "满足跨境或实体产品价值门槛"

    if eligible and not evidence_sufficient:
        eligible = False
        reason = "公开信息不足，无法可靠判断实际用途或产品化路径"

    return {
        "eligible": bool(eligible),
        "reason": reason,
        "profile": profile,
        "cross_border": cross_border,
        "technical_frontier": technical,
        "hardware_enablement": hardware,
        "physical_product": physical,
        "product_categories": product_categories,
        "evidence_sufficient": evidence_sufficient,
    }


def attach_eligibility_metrics(item: Dict, result: Dict) -> Dict:
    """把资格判断写回 metrics，方便日志、DeepSeek 和数据库追踪。"""
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics

    profile = result.get("profile") or {}
    metrics["report_eligible"] = bool(result.get("eligible"))
    metrics["evidence_sufficient"] = bool(result.get("evidence_sufficient"))
    metrics["eligibility_reason"] = str(result.get("reason") or "")
    metrics["opportunity_score"] = profile.get("opportunity_score", 0)
    metrics["opportunity_dimensions"] = dict(profile.get("dimensions") or {})
    metrics["opportunity_evidence"] = list(profile.get("evidence") or [])
    metrics["product_categories"] = list(profile.get("product_categories") or [])
    metrics["priority_tags"] = list(profile.get("tags") or [])
    return item
